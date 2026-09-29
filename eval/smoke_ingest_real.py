"""Proves the corpus_fetch -> ingest -> Qdrant wiring end to end over the REAL
fetched RFC/errata/IANA corpus, with the zero-cost HashEmbedder.

Assumes ``python -m corpus_fetch.fetch_all`` has already populated ``data/raw/`` --
this script does not fetch anything itself (same "ingest never fetches" boundary as
``ingest/run_ingest.py``). It ingests into its OWN Qdrant collection
(``data/qdrant_smoke_hash`` / ``agentic_rag_smoke_hash``), separate from any
production collection, so it's safe to run repeatedly.

``agenticrag.embed_config.SETTINGS`` is a module-level object built once at import
time from os.environ, so the env vars below MUST be set before anything under
``ingest/`` or ``agenticrag/`` is ever imported in this process.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["AGENTICRAG_EMBED_MODEL"] = "hash"
os.environ["AGENTICRAG_QDRANT"] = str(ROOT / "data" / "qdrant_smoke_hash")
os.environ["AGENTICRAG_COLLECTION"] = "agentic_rag_smoke_hash"

from agenticrag.embed_config import SETTINGS, get_qdrant_client  # noqa: E402
from ingest.run_ingest import run as run_ingest                    # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
ENTITIES_DIR = ROOT / "data" / "entities"

_results: list[tuple[str, bool]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "OK" if condition else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    _results.append((name, bool(condition)))
    return bool(condition)


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _point_count() -> int:
    client = get_qdrant_client()
    try:
        return client.count(SETTINGS.collection).count
    finally:
        client.close()


def _scroll_payloads(source_type: str) -> list[dict]:
    """Payloads for one source_type only. Real scale here is hundreds of thousands
    of points total, so this filters server-side and scrolls in batches rather than
    pulling everything into memory at once."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_qdrant_client()
    flt = Filter(must=[FieldCondition(key="source_type", match=MatchValue(value=source_type))])
    out: list[dict] = []
    try:
        offset = None
        while True:
            points, offset = client.scroll(
                SETTINGS.collection, scroll_filter=flt, limit=2000, with_payload=True, offset=offset,
            )
            out.extend(p.payload for p in points)
            if offset is None:
                break
    finally:
        client.close()
    return out


def main() -> int:
    if not (RAW_DIR / "_cache" / "rfc-index.txt").exists():
        print("[FAIL] data/raw not populated -- run `python -m corpus_fetch.fetch_all` first")
        return 1

    total_files = sum(1 for p in RAW_DIR.rglob("*") if p.is_file() and "_cache" not in p.parts)
    print(f"real corpus on disk: {total_files} files under {RAW_DIR} (excluding _cache)")

    report1 = run_ingest(recreate=True)
    count1 = _point_count()
    check(
        "Qdrant collection has a substantial point count after the first real ingest",
        count1 > 1000, f"count={count1}",
    )

    candidates = _load_jsonl(ENTITIES_DIR / "candidates.jsonl")
    errata_candidates = [c for c in candidates if c["entity_type"] == "errata"]
    check(
        "candidates.jsonl has real resolved=False errata (Reported/Rejected/Held, not yet Verified)",
        any(not c["resolved"] for c in errata_candidates),
        f"n={sum(1 for c in errata_candidates if not c['resolved'])}/{len(errata_candidates)}",
    )
    check(
        "candidates.jsonl has real resolved=True errata (status=Verified)",
        any(c["resolved"] for c in errata_candidates),
        f"n={sum(1 for c in errata_candidates if c['resolved'])}/{len(errata_candidates)}",
    )

    revisions = json.loads((ENTITIES_DIR / "revisions.json").read_text(encoding="utf-8"))
    rfc2616 = revisions.get("RFC2616", {})
    check(
        f"revisions.json reports RFC2616's real obsoleted_by chain (observed: {rfc2616.get('obsoleted_by')})",
        isinstance(rfc2616.get("obsoleted_by"), list) and len(rfc2616.get("obsoleted_by", [])) > 0,
    )

    rfc_text_payloads = _scroll_payloads("rfc_text")
    check(
        "at least one rfc_text chunk has is_current=False (a real obsoleted RFC)",
        any(p.get("is_current") is False for p in rfc_text_payloads),
        f"n_false={sum(1 for p in rfc_text_payloads if p.get('is_current') is False)}",
    )
    check(
        "at least one rfc_text chunk has is_current=True (a real current RFC)",
        any(p.get("is_current") is True for p in rfc_text_payloads),
        f"n_true={sum(1 for p in rfc_text_payloads if p.get('is_current') is True)}",
    )

    report2 = run_ingest(recreate=False)
    check(
        "re-run with zero file changes skips every file (watermark holds at real scale)",
        report2.files_skipped_unchanged == total_files,
        f"skipped={report2.files_skipped_unchanged} total={total_files}",
    )
    count2 = _point_count()
    check(
        "point count is unchanged after the zero-change re-run",
        count2 == count1, f"before={count1} after={count2}",
    )

    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    print(f"total_chunks(first ingest)={report1.total_chunks} files_processed={report1.files_processed}")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
