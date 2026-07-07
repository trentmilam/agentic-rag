"""agentic-rag LIVE DEMO -- a scripted, narrated transcript over the real,
already-ingested IETF RFC/errata/IANA corpus (321,124 chunks) plus the real
Obsoletes/Obsoleted-by supersession graph.

    cd projects/agentic-rag
    .venv/Scripts/python.exe run_demo.py

Three real questions, in order: the RFC 2616 (HTTP/1.1) obsoletion question --
IETF's own famous real 6-way supersession case, answered by the deterministic
SupersessionModule, not retrieval -- one ordinary cited-retrieval question, and
one question with nothing to do with this corpus. No mocked output -- every
line below is produced live by the real router + the real citation-gated
composer / audited compute dispatch, reusing the exact queries proven in
eval/eval_agenticrag.py. Deterministic + offline beyond the local Qdrant read
and local embedding (no live network calls).
"""
from __future__ import annotations

import sys
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(DEMO_ROOT))

from agenticrag._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()

from consilium.compute import answer_v3  # noqa: E402

from agenticrag.bootstrap import build_registry, build_router  # noqa: E402
from agenticrag.embed_config import get_embedder               # noqa: E402

BAR = "=" * 78


def ask(router, registry, embedder, n: int, question: str) -> dict:
    print(f"\n{BAR}\n  Q{n}. {question}\n{BAR}")
    print("  ... running the Qdrant vector search + citation-gated compose (~12\n"
          "  seconds on CPU; no GPU is used at query time). Working...", flush=True)
    a = answer_v3(question, registry, embedder, router)
    kind = a.get("kind")
    if kind == "abstain":
        print("  -> ABSTAINED -- honest refusal (nothing in the corpus supported "
              "an answer to this).")
    elif kind == "compute":
        aud = a["audited"]
        print(f"  -> routed to AUDITED COMPUTE  (module: {a['module']})")
        print(f"     ok={aud.get('ok')}  deterministic={aud.get('deterministic')}  "
              f"method={aud.get('method')}")
    else:  # retrieval or mixed
        print(f"  -> routed to CITED RETRIEVAL  (module(s): {a.get('module')}, "
              f"{a.get('citations', 0)} citation(s))")
        if a.get("answer"):
            flat = " ".join(a["answer"].split())
            print(f"     \"{flat[:220]}{'...' if len(flat) > 220 else ''}\"")
    return a


def main() -> int:
    print(BAR)
    print("  AGENTIC-RAG -- a real IETF RFC/errata/IANA corpus, routed and cited")
    print("  retrieval alongside a deterministic real supersession-graph lookup.")
    print(BAR)

    print("  Building the registry (Qdrant-backed; a one-time ~60s scan for the\n"
          "  poison-quarantine corpus, then queries hit Qdrant live -- progress below)...")
    embedder = get_embedder()
    registry = build_registry(embedder)
    router = build_router(registry, embedder)

    # Q1 -- the real, famous multi-way obsoletion case: RFC 2616 (HTTP/1.1) was
    # entirely superseded by six later RFCs, not one. There is no "current
    # revision" of RFC 2616's own text to retrieve -- SupersessionModule is the
    # correct, explicit path to this real fact (see eval/prove_revision_guard.py
    # for the full structural-exclusion proof).
    a1 = ask(router, registry, embedder, 1,
             "What obsoleted RFC 2616, the HTTP/1.1 specification?")
    successors = None
    if a1.get("kind") == "compute":
        successors = a1["audited"]["result"]["successors"]
    else:
        for c in a1.get("computed", []):
            if c.get("module") == "supersession":
                successors = c["audited"]["result"]["successors"]
    print(f"     real successors: {sorted(successors) if successors else successors}")

    # Q2 -- an ordinary cited-retrieval question over the real RFC full text.
    ask(router, registry, embedder, 2,
        "How does IP fragmentation and reassembly work in the Internet Protocol?")

    # Q3 -- nothing to do with this corpus. Intended behavior is an honest
    # abstain; ask() above prints whatever the live system actually does.
    ask(router, registry, embedder, 3,
        "What's the best way to season a cast iron skillet before first use?")

    print(f"\n{BAR}")
    print("  Every retrieved citation above traces to a real chunk of a real IETF")
    print("  document; every supersession fact traces to the real rfc-index.txt")
    print("  Obsoletes/Obsoleted-by graph. CITED RETRIEVAL, AUDITED COMPUTE, or an")
    print("  HONEST ABSTAIN: never a fabricated guess.")
    print(BAR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
