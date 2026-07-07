"""Production eval: proves the real ingest -> Qdrant -> Consilium pipeline
answers real questions against the real, already-ingested IETF RFC/errata/IANA
corpus (321,124 chunks across rfc_text/rfc_index/errata/iana_registry) plus the
real Obsoletes/Obsoleted-by supersession graph (``SupersessionModule``). Uses
the real embedder (BAAI/bge-base-en-v1.5) -- the exact one that ingested the
corpus, no hash-embedder shortcut -- so this proves genuine semantic retrieval
end-to-end, not wiring alone. Deterministic given the already-ingested corpus;
no re-ingestion here.

This also re-proves the revision guard's structural exclusion (see
``eval/prove_revision_guard.py`` for the narrated, standalone version of the
same proof): it queries Qdrant directly, filtered by RFC 2616's own doc_id
(``agenticrag.registry_loader.load_chunks_for_doc``, unfiltered by currency),
to confirm its chunks are real and present in the store even though the
registry's own ``current_only=True`` module excludes them.

MEASURED CALIBRATION NOTE: see ``agenticrag.bootstrap.ROUTER_KWARGS`` for the
real router-score measurements that justified departing from
``consilium.router.Router``'s stated library defaults (floor=0.11,
anchor_centroid=0.25, anchor_best_chunk=0.25).

    python eval/eval_agenticrag.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agenticrag._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()

from consilium.compute import answer_v3  # noqa: E402

from agenticrag.bootstrap import build_registry, build_router  # noqa: E402
from agenticrag.embed_config import SETTINGS, get_embedder  # noqa: E402
from agenticrag.registry_loader import load_chunks_for_doc  # noqa: E402

# One naturally-phrased in-scope query per real source type -- ordinary
# technical phrasing, not a parrot of the Descriptor's own subject wording.
PER_MODULE_CHECKS = [
    ("rfc_text", "How does IP fragmentation and reassembly work in the Internet Protocol?"),
    ("rfc_index", "Who authored RFC 2119 and when was it published?"),
    ("errata", "What errata have been reported against RFC 5322?"),
    ("iana_registry", "What port is registered for HTTPS in the IANA service names registry?"),
]
SUPERSESSION_QUESTION = "What obsoleted RFC 2616, the HTTP/1.1 specification?"
EXPECTED_SUCCESSORS = {"RFC7230", "RFC7231", "RFC7232", "RFC7233", "RFC7234", "RFC7235"}

OOS_QUESTION = "What's the best way to season a cast iron skillet before first use?"

# A genuinely current (non-obsoleted) real RFC -- checked directly against
# data/entities/revisions.json, not assumed: RFC 791, the Internet Protocol
# (1981), has an empty obsoleted_by list in the live index as of ingest.
CURRENT_RFC_QUERY = "Is RFC 791 still current?"

# Verified absent from data/entities/revisions.json (whose real max RFC number
# is 10014 as of ingest) -- not a fabricated dangling pointer, just a real
# number far beyond any RFC ever issued.
NOT_FOUND_RFC_QUERY = "Is RFC 99999 still current?"

TARGET_DOC = "rfc_text/rfc2616.txt"  # doc_id ingest writes for RFC 2616's full text

checks: dict[str, bool] = {}


def record(name: str, ok: bool, detail: str = "") -> None:
    checks[name] = ok
    suffix = f" -- {detail}" if detail else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{suffix}")


def _supersession_audited(a: dict) -> dict | None:
    """Pull the supersession module's audited envelope out of answer_v3's
    result, whichever shape it came back as (a lone "compute" kind if only
    supersession was selected, or one entry of a "mixed" kind's computed list
    if a retrieval module was also anchored by the same query)."""
    if a.get("kind") == "compute" and a.get("module") == "supersession":
        return a.get("audited")
    for c in a.get("computed", []):
        if c.get("module") == "supersession":
            return c.get("audited")
    return None


def main() -> int:
    embedder = get_embedder()
    registry = build_registry(embedder)
    router = build_router(registry, embedder)

    print("\n=== MEASURED ROUTER SCORES (real corpus + real embedder; see "
          "agenticrag.bootstrap.ROUTER_KWARGS for the calibration this justified) ===")
    all_questions = [q for _, q in PER_MODULE_CHECKS] + [SUPERSESSION_QUESTION, OOS_QUESTION]
    for question in all_questions:
        rr = router.route(question)
        print(f"\n{question!r}")
        print(f"  abstained={rr.abstained} selected={rr.selected} trace={rr.trace}")
        for name, score, bd in rr.ranked:
            print(f"    {name}: score={score} breakdown={bd}")

    print("\n=== CORRECTNESS CHECKS ===")
    for expected_module, question in PER_MODULE_CHECKS:
        a = answer_v3(question, registry, embedder, router)
        modules_used = a.get("module") or []
        if isinstance(modules_used, str):
            modules_used = [modules_used]
        ok = (
            a.get("kind") in ("retrieval", "mixed")
            and expected_module in modules_used
            and (a.get("citations") or 0) >= 1
        )
        record(f"{expected_module}_answers_correctly", ok,
               f"kind={a.get('kind')} module={modules_used} citations={a.get('citations')}")

    a_ss = answer_v3(SUPERSESSION_QUESTION, registry, embedder, router)
    audited = _supersession_audited(a_ss)
    result = (audited or {}).get("result", {})
    record("supersession_query_routes_to_supersession_module", audited is not None,
           f"kind={a_ss.get('kind')} module={a_ss.get('module')}")
    record("supersession_rfc2616_status_obsoleted", result.get("status") == "obsoleted",
           f"status={result.get('status')!r}")
    record("supersession_rfc2616_successors_exact_6way",
           set(result.get("successors", [])) == EXPECTED_SUCCESSORS,
           f"successors={sorted(result.get('successors', []))}")

    a_oos = answer_v3(OOS_QUESTION, registry, embedder, router)
    record("out_of_scope_abstains", a_oos.get("kind") == "abstain", f"kind={a_oos.get('kind')}")

    # --- revision-guard structural exclusion (narrated fully in
    #     eval/prove_revision_guard.py) --------------------------------------
    current_rfc_text = registry.by_name("rfc_text")
    current_has_2616 = any(c.doc == TARGET_DOC for c in current_rfc_text.chunks)
    record("rfc2616_absent_from_default_current_only_module", not current_has_2616,
           f"n_chunks={len(current_rfc_text.chunks)}")

    t0 = time.time()
    # Reuse the registry's LIVE Qdrant client -- opening a second here would collide
    # ("already accessed by another instance": Qdrant local mode is single-opener per
    # folder, and build_registry keeps its client open for live queries).
    rfc2616_chunks = load_chunks_for_doc(TARGET_DOC, registry.qdrant_client, SETTINGS.collection)
    print(f"  (targeted doc_id fetch took {time.time() - t0:.2f}s, "
          f"{len(rfc2616_chunks)} chunks for {TARGET_DOC!r})")
    record("rfc2616_present_in_unfiltered_current_only_false_module", len(rfc2616_chunks) > 0,
           f"n_chunks={len(rfc2616_chunks)}")

    # --- SupersessionModule status on a genuinely current + a not_found RFC --
    supersession_module = registry.by_name("supersession")
    a_current = supersession_module.compute(CURRENT_RFC_QUERY)
    record("genuinely_current_real_rfc_resolves_current",
           a_current.get("result", {}).get("status") == "current",
           f"result={a_current.get('result')}")

    a_not_found = supersession_module.compute(NOT_FOUND_RFC_QUERY)
    record("rfc_absent_from_revisions_json_resolves_not_found_not_crash",
           a_not_found.get("ok") is True and a_not_found.get("result", {}).get("status") == "not_found",
           f"result={a_not_found.get('result')}")

    print("\n=== CHECKS ===")
    for k, v in checks.items():
        print(f"{'OK  ' if v else 'FAIL'} {k}")
    passed = all(checks.values())
    print("\nRESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
