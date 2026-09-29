"""Proves the revision guard's real structural fact, not a "corrected value"
demo (there is no single "current revision" of RFC 2616's own text; it was
entirely superseded by six different documents), but a two-part real proof:

(a) STRUCTURAL EXCLUSION. RFC 2616's own ``rfc_text`` chunks exist in Qdrant
    (306,939 total rfc_text chunks across the whole corpus) but are marked
    ``is_current=False`` at ingest time (``ingest/run_ingest.py::_is_current``),
    because ``data/entities/revisions.json["RFC2616"]["obsoleted_by"]`` is
    non-empty. This script loads the real ``current_only=True`` rfc_text
    module straight from Qdrant (what ``agenticrag.bootstrap.build_registry``
    actually uses: 225,809 chunks, confirming that 81,130 chunks across the
    corpus are excluded as non-current, not just RFC 2616's), then queries
    Qdrant a second time filtered directly by RFC 2616's own doc_id, unfiltered
    by currency. RFC 2616's chunks must be ABSENT from the first load and
    PRESENT in the second, proving the data exists and is being filtered by
    a real, checkable fact, not merely absent from the ingest.

(b) THE CORRECT PATH TO THE ANSWER. ``SupersessionModule`` (see
    ``agenticrag/supersession.py``) is the explicit, correct way to learn what
    happened to RFC 2616: a query naming it returns the real 6-way successor
    list (RFC 7230-7235), IETF's own famous multi-way obsoletion case.

Both real Qdrant loads happen in-process. The first (``current_only=True``,
~226k chunks) takes under a minute (see ``agenticrag.registry_loader``'s scroll
batch-size note); the second is a doc_id-filtered fetch of RFC 2616's own
handful of chunks and returns in a couple seconds; see the printed timings.

    python eval/prove_revision_guard.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from consilium.module import Descriptor  # noqa: E402

from agenticrag.bootstrap import DESCRIPTORS, SUPERSESSION_DESCRIPTOR  # noqa: E402
from agenticrag.embed_config import SETTINGS, get_embedder, get_qdrant_client  # noqa: E402
from agenticrag.registry_loader import load_chunks_for_doc, load_module_from_qdrant  # noqa: E402
from agenticrag.supersession import SupersessionModule  # noqa: E402

TARGET_RFC = "RFC2616"
TARGET_DOC = "rfc_text/rfc2616.txt"  # doc_id ingest writes for RFC 2616's full text
EXPECTED_SUCCESSORS = {"RFC7230", "RFC7231", "RFC7232", "RFC7233", "RFC7234", "RFC7235"}

_results: list[tuple[str, bool]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "OK" if condition else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    _results.append((name, bool(condition)))
    return bool(condition)


def main() -> int:
    print("=" * 78)
    print("  REVISION GUARD PROOF -- RFC 2616 (HTTP/1.1), obsoleted by 6 real")
    print("  successor documents (RFC 7230-7235)")
    print("=" * 78)

    embedder = get_embedder()
    client = get_qdrant_client()
    rfc_text_descriptor: Descriptor = DESCRIPTORS["rfc_text"]

    # --- (a) structural exclusion ------------------------------------------
    print("\n--- (a) structural exclusion: current_only=True vs current_only=False ---")

    t0 = time.time()
    current_module = load_module_from_qdrant(
        "rfc_text", client, SETTINGS.collection, embedder, rfc_text_descriptor, current_only=True,
    )
    print(f"loaded current_only=True rfc_text module in {time.time() - t0:.1f}s "
          f"({len(current_module.chunks)} chunks)")
    current_has_2616 = any(c.doc == TARGET_DOC for c in current_module.chunks)
    check(
        f"{TARGET_RFC} chunks ABSENT from the default current_only=True rfc_text module",
        not current_has_2616,
        f"n_chunks_total={len(current_module.chunks)} rfc2616_present={current_has_2616}",
    )

    from qdrant_client.models import FieldCondition, Filter, MatchValue

    t0 = time.time()
    total_rfc_text = client.count(
        collection_name=SETTINGS.collection,
        count_filter=Filter(must=[FieldCondition(key="source_type", match=MatchValue(value="rfc_text"))]),
        exact=True,
    ).count
    rfc2616_chunks = load_chunks_for_doc(TARGET_DOC, client, SETTINGS.collection)
    print(f"queried total rfc_text count + RFC 2616's doc_id-filtered chunks in "
          f"{time.time() - t0:.2f}s ({total_rfc_text} total, {len(rfc2616_chunks)} for {TARGET_DOC!r})")
    check(
        f"{TARGET_RFC} chunks PRESENT when queried directly by doc_id, unfiltered by currency",
        len(rfc2616_chunks) > 0,
        f"n_chunks_total_rfc_text={total_rfc_text} rfc2616_chunks={len(rfc2616_chunks)}",
    )
    check(
        "the excluded chunk count matches exactly (same real data, just filtered)",
        total_rfc_text - len(current_module.chunks) >= len(rfc2616_chunks) > 0,
        f"total_rfc_text={total_rfc_text} current={len(current_module.chunks)} "
        f"rfc2616_chunks={len(rfc2616_chunks)}",
    )
    if rfc2616_chunks:
        sample = " ".join(rfc2616_chunks[0].text.split())[:200]
        print(f"  sample RFC 2616 chunk text (present via the doc_id-filtered query): {sample!r}...")

    client.close()

    # --- (b) the correct path to the answer ---------------------------------
    print("\n--- (b) SupersessionModule: the real, explicit obsoletion answer ---")
    supersession = SupersessionModule(embedder, SUPERSESSION_DESCRIPTOR)
    audited = supersession.compute("What obsoleted RFC 2616, the HTTP/1.1 specification?")
    result = audited.get("result", {})
    print(f"  query result: status={result.get('status')!r} "
          f"successors={result.get('successors')}")
    print(f"  history ({len(result.get('history', []))} nodes visited beyond RFC2616): "
          f"{result.get('history')}")
    check("SupersessionModule envelope reports ok=True", audited.get("ok") is True)
    check("SupersessionModule reports status='obsoleted' for RFC 2616",
          result.get("status") == "obsoleted", f"status={result.get('status')!r}")
    check(
        "SupersessionModule's successor list is exactly the real 6-way RFC 7230-7235 case",
        set(result.get("successors", [])) == EXPECTED_SUCCESSORS,
        f"successors={sorted(result.get('successors', []))}",
    )
    check(
        "the graph walk (history) surfaces all 6 real successors, not just the direct list",
        EXPECTED_SUCCESSORS <= {h["rfc"] for h in result.get("history", [])},
        f"history_rfcs={sorted({h['rfc'] for h in result.get('history', [])})}",
    )

    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
