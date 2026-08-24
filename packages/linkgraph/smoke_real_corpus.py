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

    # Every number the README quotes is asserted here, not merely printed. Printing
    # them let the published figures drift from what the code actually produces with
    # nothing to catch it -- a bare `corrects > 0` passes just as happily on a graph
    # half this size. Update these only alongside the README, and say why.
    EXPECTED_MENTIONS = 21830
    EXPECTED_NODES = 13666
    EXPECTED_EDGES = 14844
    EXPECTED_EDGE_COUNTS = {
        "co_mentions": 5061,
        "obsoletes": 2370,
        "updates": 2352,
        "corrects": 5061,
    }

    checks = [
        ("mention_count", len(refs), EXPECTED_MENTIONS),
        ("node_count", len(g.nodes), EXPECTED_NODES),
        ("edge_count", len(g.edges), EXPECTED_EDGES),
    ] + [
        (f"edge_type_{name}", edge_counts.get(name, 0), expected)
        for name, expected in EXPECTED_EDGE_COUNTS.items()
    ]

    print()
    failed = 0
    for name, actual, expected in checks:
        good = actual == expected
        failed += not good
        suffix = "" if good else f"  (README publishes {expected})"
        print(f"{'OK  ' if good else 'FAIL'} {name} = {actual}{suffix}")

    print("\nRESULT:", "PASS" if not failed else f"FAIL ({failed} of {len(checks)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
