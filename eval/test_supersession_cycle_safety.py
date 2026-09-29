"""Dedicated unit test: agenticrag.supersession._walk_supersession's cycle
safety and its defensive node cap, both exercised on a SYNTHETIC graph only.

No cycle is expected to exist in genuine IETF data (a real RFC cannot obsolete
itself through a chain of real successors), so this deliberately does NOT use
a real-shaped "RFC<n>" id to build one; that would misstate a real document.
"RFCX1"/"RFCX2"/... are permanently-safe, non-numeric-shaped node names built
by hand for this test only; ``_extract_rfc_key``'s regex (\\bRFC\\s*(\\d+)\\b)
cannot even match them, so they can never be confused with a real RFC number
anywhere else in this codebase.

Fast and fully offline: no corpus, no embedder, no Qdrant.

    python eval/test_supersession_cycle_safety.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agenticrag.supersession import _walk_supersession  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "OK" if condition else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    _results.append((name, bool(condition)))
    return bool(condition)


# --- pytest-collectible tests (real ``def test_*`` so ``pytest`` actually runs
#     this safety-critical suite, not just the ``python <file>`` runner below) ---
def test_two_node_cycle_terminates_and_visits_other_node_once():
    cyclic_graph = {
        "RFCX1": {"obsoletes": ["RFCX2"], "obsoleted_by": []},
        "RFCX2": {"obsoletes": ["RFCX1"], "obsoleted_by": []},
    }
    history = _walk_supersession("RFCX1", cyclic_graph)
    assert history == [{"rfc": "RFCX2", "relation": "obsoletes", "hops": 1}], history


def test_self_loop_terminates_with_nothing_beyond_start():
    self_loop_graph = {"RFCX1": {"obsoletes": ["RFCX1"], "obsoleted_by": []}}
    assert _walk_supersession("RFCX1", self_loop_graph) == []


def test_chain_walk_respects_50_node_defensive_cap():
    chain_graph = {
        f"RFCX{i}": {"obsoletes": [], "obsoleted_by": ([f"RFCX{i + 1}"] if i < 60 else [])}
        for i in range(1, 61)
    }
    history_chain = _walk_supersession("RFCX1", chain_graph, max_nodes=50)
    visited_count = len({"RFCX1", *(h["rfc"] for h in history_chain)})
    assert visited_count <= 50, f"visited={visited_count}"


def test_three_way_branch_reaches_all_successors_plus_predecessor():
    branch_graph = {
        "RFC2616": {"obsoletes": [2068], "obsoleted_by": [7230, 7231, 7232]},
        "RFC2068": {"obsoletes": [], "obsoleted_by": [2616]},
        "RFC7230": {"obsoletes": [2616], "obsoleted_by": []},
        "RFC7231": {"obsoletes": [2616], "obsoleted_by": []},
        "RFC7232": {"obsoletes": [2616], "obsoleted_by": []},
    }
    reached = {h["rfc"] for h in _walk_supersession("RFC2616", branch_graph)}
    assert reached == {"RFC2068", "RFC7230", "RFC7231", "RFC7232"}, sorted(reached)


def main() -> int:
    # A two-node cycle: RFCX1 obsoletes RFCX2, and RFCX2 obsoletes RFCX1 right
    # back. Purely synthetic; this shape cannot occur in genuine IETF data.
    cyclic_graph = {
        "RFCX1": {"obsoletes": ["RFCX2"], "obsoleted_by": []},
        "RFCX2": {"obsoletes": ["RFCX1"], "obsoleted_by": []},
    }
    history = _walk_supersession("RFCX1", cyclic_graph)
    check(
        "two-node cycle terminates and visits the other node exactly once",
        history == [{"rfc": "RFCX2", "relation": "obsoletes", "hops": 1}],
        f"history={history}",
    )

    # A self-loop: RFCX1 "obsoletes" itself. Even more degenerate than a real
    # cycle: must not infinite-loop or re-add the start node as its own neighbor.
    self_loop_graph = {"RFCX1": {"obsoletes": ["RFCX1"], "obsoleted_by": []}}
    history_self = _walk_supersession("RFCX1", self_loop_graph)
    check(
        "self-loop terminates with nothing visited beyond the start",
        history_self == [],
        f"history={history_self}",
    )

    # A 60-node synthetic chain exceeds the 50-node defensive cap. The walk
    # must stop ADMITTING new nodes at the cap rather than silently ignoring it.
    chain_graph = {
        f"RFCX{i}": {"obsoletes": [], "obsoleted_by": ([f"RFCX{i + 1}"] if i < 60 else [])}
        for i in range(1, 61)
    }
    history_chain = _walk_supersession("RFCX1", chain_graph, max_nodes=50)
    visited_count = len({"RFCX1", *(h["rfc"] for h in history_chain)})
    check(
        "60-node chain walk respects the 50-node defensive cap",
        visited_count <= 50,
        f"visited={visited_count}",
    )

    # A real-shaped many-to-many branch (NOT synthetic: a small hand-built
    # subset shaped like RFC 2616's own real graph, to prove branching itself
    # works before the full real-corpus proof in prove_revision_guard.py runs
    # against the actual data): one node obsoleted by three others.
    branch_graph = {
        "RFC2616": {"obsoletes": [2068], "obsoleted_by": [7230, 7231, 7232]},
        "RFC2068": {"obsoletes": [], "obsoleted_by": [2616]},
        "RFC7230": {"obsoletes": [2616], "obsoleted_by": []},
        "RFC7231": {"obsoletes": [2616], "obsoleted_by": []},
        "RFC7232": {"obsoletes": [2616], "obsoleted_by": []},
    }
    history_branch = _walk_supersession("RFC2616", branch_graph)
    reached = {h["rfc"] for h in history_branch}
    check(
        "three-way branch reaches all three successors plus the predecessor",
        reached == {"RFC2068", "RFC7230", "RFC7231", "RFC7232"},
        f"reached={sorted(reached)}",
    )

    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
