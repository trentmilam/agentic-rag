"""Ingest orchestrator: data/raw/<source_type>/ -> connector.extract() -> chunk -> embed -> Qdrant.

Every connector's ``extract()`` always runs (cheap, no I/O beyond one file read) so
``candidates.jsonl`` reflects the exact current file set every run; only the expensive
chunk+embed+upsert steps are skipped for files whose content hash matches
``data/state.json`` from the previous run.

This never fetches anything over the network itself: ``python -m
corpus_fetch.fetch_all`` is a distinct, explicit, separately-run step that must
already have populated ``data/raw/`` before ``run()`` is called.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agenticrag.embed_config import (                           # noqa: E402
    SETTINGS, get_embedder, get_qdrant_client, record_embedder_marker,
)
from corpus_fetch.fetch_rfc_index import parse_rfc_index        # noqa: E402
from ingest.connectors import errata, iana_registry, rfc_index, rfc_text  # noqa: E402
from ingest.connectors.base import ExtractedDoc                 # noqa: E402
from ingest.entities import EntityRef                            # noqa: E402
from ingest.state import changed_files, load_state, save_state  # noqa: E402

from ragpack.chunk import chunk_text, classify_chunk, content_hash, stable_id  # noqa: E402
from ragpack.store import ensure_collection, upsert              # noqa: E402

CONNECTORS = {
    "rfc_index": rfc_index,
    "rfc_text": rfc_text,
    "errata": errata,
    "iana_registry": iana_registry,
}

# The embed/upsert loop is the heavy step (minutes on a small corpus, hours on the
# full 321k-chunk one) with no other output of its own, so print a heartbeat at most
# this often so a long run reads as progress, not a hang.
_PROGRESS_INTERVAL_SECS = 15


@dataclass
class DocReport:
    doc_id: str
    source_type: str
    n_chunks: int


@dataclass
class IngestReport:
    collection: str
    model: str
    total_chunks: int
    files_processed: int
    files_skipped_unchanged: int
    documents: list = field(default_factory=list)


def _iter_raw_files(raw_dir: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for source_type in CONNECTORS:
        source_dir = raw_dir / source_type
        if not source_dir.is_dir():
            continue
        out.extend((source_type, path) for path in sorted(source_dir.rglob("*")) if path.is_file())
    return out


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entity_ids_in_chunk(entities: list[EntityRef], chunk: str) -> list[str]:
    chunk_lower = chunk.lower()
    return sorted({e.entity_id for e in entities if e.raw_text.lower() in chunk_lower})


def _is_current(doc: ExtractedDoc, revisions_index: dict) -> bool:
    """A document with no single-revision concept (an erratum, an IANA registry:
    neither names one specific RFC revision the way a procedure once named one part
    revision) is never stale as a WHOLE document, so it defaults current=True.

    For an ``rfc_text``/``rfc_index`` document (``doc.part_number`` holds
    ``f"RFC{n}"``), currency is the real fact the IETF supersession graph records:
    current iff nothing obsoletes it (``obsoleted_by`` is empty), not a
    part+revision-equality check like the old pump-corpus domain used, since RFC full
    text has no "revision" of its own; a new number entirely replaces it.
    """
    if doc.source_type not in ("rfc_text", "rfc_index"):
        return True
    key = doc.part_number
    if not key:
        return True
    entry = revisions_index.get(key)
    if entry is None:
        return True
    return len(entry.get("obsoleted_by", [])) == 0


def _force_clear_local_collection() -> None:
    """qdrant-client's local-mode ``delete_collection`` does
    ``shutil.rmtree(path, ignore_errors=True)``. On Windows this can silently fail
    (transient file lock) and leave the old collection directory in place, so a
    "recreated" collection actually re-attaches to old data instead of starting empty.
    Delete the physical directory ourselves first, with errors surfaced instead of
    swallowed, so --recreate is trustworthy."""
    if not SETTINGS.qdrant or SETTINGS.qdrant == ":memory:" or SETTINGS.qdrant.startswith(("http://", "https://")):
        return
    collection_dir = Path(SETTINGS.qdrant) / "collection" / SETTINGS.collection
    if collection_dir.exists():
        shutil.rmtree(collection_dir)


def run(*, recreate: bool = False, data_dir: Path | None = None) -> IngestReport:
    data_dir = Path(data_dir).resolve() if data_dir else (REPO_ROOT / "data")
    raw_dir = data_dir / "raw"
    state_path = data_dir / "state.json"
    entities_dir = data_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    all_files = _iter_raw_files(raw_dir)
    hashes = {
        str(path.relative_to(data_dir)).replace("\\", "/"): _file_hash(path)
        for _, path in all_files
    }
    # recreate=True means "rebuild everything": honoring a stale watermark here would
    # skip re-embedding into what is now a freshly emptied collection, silently leaving
    # it empty. Treating every file as new when recreating keeps --recreate trustworthy.
    old_state = {} if recreate else load_state(state_path)
    # changed_files round-trips each key through Path, which normalizes to native
    # (backslash, on Windows) separators on str(); re-flip to forward slashes so
    # this set compares equal to the forward-slash-normalized `rel` keys below.
    changed = {str(p).replace("\\", "/") for p in changed_files(hashes, old_state)}

    print(
        f"ingest: {len(all_files)} files found, {len(changed)} changed since last run "
        f"({len(all_files) - len(changed)} unchanged, skipped) -- chunking+embedding the "
        "changed set now",
        flush=True,
    )

    if recreate:
        _force_clear_local_collection()

    # The full live index (all 9,000+ RFCs, not just the text-fetch subset) matters
    # because a supersession chain can point outside the subset, and it's cheap: just a
    # local-file re-parse, no network call.
    full_index = parse_rfc_index(raw_dir / "_cache" / "rfc-index.txt")
    revisions_index = rfc_index.build_revisions_index(full_index)

    embedder = get_embedder()
    client = get_qdrant_client()
    ensure_collection(client, SETTINGS.collection, embedder.dim, recreate=recreate)
    record_embedder_marker(recreate=recreate)

    doc_reports: list[DocReport] = []
    all_entities: list[EntityRef] = []
    total_chunks = 0
    files_processed = 0
    files_skipped = 0
    last_progress = time.monotonic()

    for source_type, path in all_files:
        rel = str(path.relative_to(data_dir)).replace("\\", "/")
        connector = CONNECTORS[source_type]
        doc = connector.extract(path)
        all_entities.extend(doc.entities)

        if rel not in changed:
            files_skipped += 1
            continue
        files_processed += 1

        chunks = chunk_text(doc.text, max_chars=1200, overlap=150)
        is_current = _is_current(doc, revisions_index)

        ids, texts, payloads = [], [], []
        for i, chunk in enumerate(chunks):
            chash = content_hash(chunk)
            ids.append(stable_id("agentic-rag", doc.doc_id, i, chash))
            texts.append(chunk)
            payloads.append({
                "source_type": source_type,
                "doc_id": doc.doc_id,
                "part_number": doc.part_number,
                "revision": doc.revision,
                "chunk_index": i,
                "text": chunk,
                "chunk_type": classify_chunk(chunk, path.suffix),
                "content_hash": chash,
                "entity_ids": _entity_ids_in_chunk(doc.entities, chunk),
                "is_current": is_current,
            })

        for start in range(0, len(ids), SETTINGS.batch_size):
            batch_ids = ids[start:start + SETTINGS.batch_size]
            batch_texts = texts[start:start + SETTINGS.batch_size]
            batch_payloads = payloads[start:start + SETTINGS.batch_size]
            vectors = embedder.embed(batch_texts)
            upsert(client, SETTINGS.collection, batch_ids, vectors, batch_payloads)

            now = time.monotonic()
            if now - last_progress >= _PROGRESS_INTERVAL_SECS:
                print(
                    f"  ... {files_processed}/{len(changed)} changed files, "
                    f"{total_chunks + start + len(batch_ids)} chunks embedded so far",
                    flush=True,
                )
                last_progress = now

        doc_reports.append(DocReport(doc_id=doc.doc_id, source_type=source_type, n_chunks=len(chunks)))
        total_chunks += len(chunks)

    client.close()

    with (entities_dir / "candidates.jsonl").open("w", encoding="utf-8") as f:
        for ent in all_entities:
            f.write(json.dumps(asdict(ent)) + "\n")
    (entities_dir / "revisions.json").write_text(
        json.dumps(revisions_index, indent=2, sort_keys=True), encoding="utf-8",
    )
    save_state(state_path, hashes)

    return IngestReport(
        collection=SETTINGS.collection, model=SETTINGS.model, total_chunks=total_chunks,
        files_processed=files_processed, files_skipped_unchanged=files_skipped,
        documents=[asdict(d) for d in doc_reports],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    report = run(recreate=args.recreate, data_dir=Path(args.data_dir) if args.data_dir else None)
    print(json.dumps(asdict(report), indent=2))
