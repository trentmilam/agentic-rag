"""Proves ``resolve.build_graph`` recovers real graph structure -- including a
non-zero ``corrects`` edge count -- from the REAL agentic-rag entity-mention
export, not just the hand-built fixture ``eval.py``/``pytest`` exercise.

Assumes agentic-rag's ingest has already produced
``agentic-rag/data/entities/candidates.jsonl`` -- this script does not fetch
or ingest anything itself, it only reads that file via linkgraph's own
``adapter.load_from_export``.

    python smoke_real_corpus.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from linkgraph import adapter, resolve  # noqa: E402

CANDIDATES_PATH = os.path.join(
    ROOT, "..", "agentic-rag", "data", "entities", "candidates.jsonl"
)


def main() -> int:
    path = os.path.abspath(CANDIDATES_PATH)
    if not os.path.exists(path):
        print(f"[FAIL] real corpus not found at {path}")
        return 1

    refs = adapter.load_from_export(path)
    print(f"loaded {len(refs)} EntityRef mentions from {path}")

    g = resolve.build_graph(refs)
    edge_counts = Counter(e.edge_type for e in g.edges)
    print(f"built graph: {len(g.nodes)} nodes, {len(g.edges)} edges")
    print("\n=== real edge-type counts ===")
    for edge_type in ("co_mentions", "obsoletes", "updates", "corrects"):
        print(f"  {edge_type:12s} {edge_counts.get(edge_type, 0)}")

    corrects = edge_counts.get("corrects", 0)
    ok = corrects > 0
    print(f"\n{'OK  ' if ok else 'FAIL'} corrects_count_positive (corrects={corrects})")
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
