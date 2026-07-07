"""Fixture-only tests for agenticrag.mcp.server.

Built entirely against hand-constructed fakes and a tiny synthetic corpus -- no
``mcp`` package, no real embedder, no Qdrant, no network. The fakes stand in for
the real ``consilium.router.RouteResult`` / ``consilium.registry.Registry`` /
embedder, but are plain local objects.

The ``search`` tool wraps ``consilium.compute.answer_v3`` verbatim, so these
tests drive the *real* ``answer_v3`` with a faked router/registry/embedder and
assert the wrapper adds nothing:
  * an honest abstain passes straight through, unmodified;
  * a healthy (compute-path) answer passes straight through too.

The relationship tools are covered on BOTH branches of their one stable envelope:
  * the failure branch -- degrade to ``{"ok": False, ..., "fallback": ...}`` when
    the ``agenticrag.relationships`` bridge is unimportable (simulated
    deterministically, see ``_simulate_missing_relationships_bridge``);
  * the success branch -- ``{"ok": True, ..., "result": ...}`` driven through the
    REAL linkgraph-backed bridge against a small synthetic ``candidates.jsonl``
    (the ``_real_bridge_over_synthetic_corpus`` pytest fixture). The success-path
    tests are pytest-only (they need ``tmp_path``/``monkeypatch``); the ``__main__``
    runner below covers the wrapper + fallback cases.

Run directly (prints a literal PASS/FAIL line per case; success-path tests run
only under pytest):
    .venv/Scripts/python.exe agenticrag/mcp/test_server.py
or under pytest:
    .venv/Scripts/python.exe -m pytest agenticrag/mcp/test_server.py -q
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import dataclass, field

import pytest

# Make `import agenticrag...` work when run as a bare script from any cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agenticrag.mcp import server  # noqa: E402  (add_sibling_paths runs on import)


# ---------------------------------------------------------------------------
# Fakes -- shapes mirror consilium.router.RouteResult (query, ranked, selected,
# abstained, trace) and a minimal Registry/embedder. See consilium/router.py.
# ---------------------------------------------------------------------------
@dataclass
class FakeRouteResult:
    query: str = "q"
    ranked: list = field(default_factory=list)   # [(module_name, score, breakdown)]
    selected: list = field(default_factory=list)
    abstained: bool = False
    trace: dict = field(default_factory=dict)


class FakeRouter:
    """Returns a preset RouteResult -- no scoring, no embedder use."""
    def __init__(self, result: FakeRouteResult):
        self._result = result

    def route(self, query: str) -> FakeRouteResult:
        return self._result


class FakeEmbedder:
    """Never actually exercised on the abstain / single-compute paths (the
    router is faked and FinanceComputeModule.compute() parses text, not vectors),
    but present so the RagContext is fully populated."""
    def embed_one(self, text):
        return [0.0]

    def embed(self, texts):
        return [[0.0] for _ in texts]


class FakeRegistry:
    def __init__(self, modules):
        self._by = {m.name: m for m in modules}

    def by_name(self, name):
        return self._by[name]


def _ctx(router, registry=None):
    return server.RagContext(
        registry=registry if registry is not None else FakeRegistry([]),
        embedder=FakeEmbedder(),
        router=router,
    )


# ---------------------------------------------------------------------------
# tool_search
#   check_* helpers assert AND return the payload (used by the __main__ runner to
#   print literal output); the test_* wrappers are pytest's assert-only entry
#   points (return None, so pytest raises no return-not-None warning).
# ---------------------------------------------------------------------------
def check_search_abstain() -> dict:
    """An honest abstain from answer_v3 must reach the caller verbatim."""
    ranked = [("rfc_text", 0.05, {}), ("errata", 0.02, {})]
    router = FakeRouter(FakeRouteResult(abstained=True, ranked=ranked, selected=[]))
    out = server.tool_search("what's the best way to season a cast iron skillet?", _ctx(router))

    assert out == {"kind": "abstain", "routing": ranked}, out
    # The wrapper adds no keys and papers over nothing.
    assert set(out.keys()) == {"kind", "routing"}, out
    return out


def check_search_healthy_compute() -> dict:
    """A non-abstain (single compute module) answer_v3 result also passes through
    verbatim -- proving the wrapper isn't abstain-only special-cased."""
    from consilium.compute import make_finance_module

    quant = make_finance_module(FakeEmbedder(), name="quant")   # real ComputeModule
    registry = FakeRegistry([quant])
    router = FakeRouter(FakeRouteResult(
        abstained=False, selected=["quant"], ranked=[("quant", 0.9, {"floor": 0.3})]))

    q = "value a call option spot 100 strike 105 t 1 r 0.02 vol 0.2"
    out = server.tool_search(q, _ctx(router, registry))

    assert out["kind"] == "compute", out
    assert out["module"] == "quant", out
    assert out["audited"]["ok"] is True, out
    assert out["audited"]["tool"] == "black_scholes", out
    return out


# ---------------------------------------------------------------------------
# relationship tools -- bridge unimportable/broken -> documented fallback
# envelope. ``agenticrag.relationships`` is now a real, working module (see its
# own docstring), so these tests can no longer rely on an accident of it not
# existing on disk; instead they force ``server._call_bridge``'s
# ``from agenticrag import relationships`` to fail deterministically.
# ---------------------------------------------------------------------------
_MISSING = object()  # sentinel: "key/attr was absent before we touched it"


@contextlib.contextmanager
def _simulate_missing_relationships_bridge():
    """Force ``from agenticrag import relationships`` (as done inside
    ``server._call_bridge``) to raise ``ImportError``, deterministically,
    regardless of the real bridge module being importable on disk.

    Two things have to be undone for the standard "poison sys.modules with
    None" trick to work here: (1) set ``sys.modules["agenticrag.relationships"]
    = None`` -- the documented way to make an import of that dotted name raise
    ``ModuleNotFoundError``; and (2) also remove the ``relationships``
    attribute Python auto-installs on the parent ``agenticrag`` package after
    any successful import, because ``from agenticrag import relationships``
    resolves via that cached attribute first and would never consult
    ``sys.modules`` at all if the attribute were left in place. Both are
    restored on exit, so this leaves no trace for other tests/import order.
    """
    import agenticrag as _agenticrag_pkg

    name = "agenticrag.relationships"
    had_attr = hasattr(_agenticrag_pkg, "relationships")
    prev_attr = getattr(_agenticrag_pkg, "relationships", None)
    prev_sys_modules = sys.modules.get(name, _MISSING)

    if had_attr:
        delattr(_agenticrag_pkg, "relationships")
    sys.modules[name] = None
    try:
        yield
    finally:
        if prev_sys_modules is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prev_sys_modules
        if had_attr:
            setattr(_agenticrag_pkg, "relationships", prev_attr)


def _assert_fallback(out: dict, tool: str) -> dict:
    assert out["ok"] is False, out
    assert out["tool"] == tool, out
    assert out["fallback"] == "use search for direct obsoletion questions", out
    assert "relationships" in out["error"], out
    return out


def check_get_related_fallback() -> dict:
    with _simulate_missing_relationships_bridge():
        return _assert_fallback(server.tool_get_related("rfc-2616", max_hops=2), "get_related")


def check_get_obsoletion_chain_fallback() -> dict:
    with _simulate_missing_relationships_bridge():
        return _assert_fallback(server.tool_get_obsoletion_chain("2616"), "get_obsoletion_chain")


def check_get_corrections_fallback() -> dict:
    with _simulate_missing_relationships_bridge():
        return _assert_fallback(server.tool_get_corrections("5322"), "get_corrections")


# -- pytest entry points (assert-only, return None) --------------------------
def test_search_passes_abstain_through_unmodified():
    check_search_abstain()


def test_search_passes_healthy_compute_answer_through():
    check_search_healthy_compute()


def test_get_related_falls_back_when_bridge_missing():
    check_get_related_fallback()


def test_get_obsoletion_chain_falls_back_when_bridge_missing():
    check_get_obsoletion_chain_fallback()


def test_get_corrections_falls_back_when_bridge_missing():
    check_get_corrections_fallback()


# ---------------------------------------------------------------------------
# relationship tools -- REAL linkgraph-backed SUCCESS path (the other branch of
# the one stable envelope: {"ok": True, "tool", "result"}). Driven through the
# real agenticrag.relationships bridge + real linkgraph over a tiny synthetic
# candidates.jsonl -- no corpus, no Qdrant, no network. Pytest-only (needs
# tmp_path/monkeypatch), so these are not in the __main__ runner above.
# ---------------------------------------------------------------------------
# One JSON object per line, per linkgraph/contract.py's candidates.jsonl contract,
# mirroring the REAL corpus's exact field shapes (checked against the real file):
# an rfc's obsoleted_by holds bare ints, but an erratum's extra["rfc"] is the
# full "RFC<n>" string. A shrunk mirror of a real fact set: RFC 2616 obsoleted by
# RFC 7230, plus one Verified erratum correcting RFC 2616.
_SYNTHETIC_CANDIDATES = [
    {"entity_type": "rfc", "entity_id": "RFC2616", "raw_text": "RFC 2616",
     "doc_id": "rfc_index/rfc2616.txt", "resolved": True,
     "extra": {"obsoletes": [], "obsoleted_by": [7230], "updates": [], "updated_by": []}},
    {"entity_type": "errata", "entity_id": "100", "raw_text": "Errata 100",
     "doc_id": "errata/erratum_100.txt", "resolved": True,
     "extra": {"status": "Verified", "type": "Editorial", "rfc": "RFC2616"}},
]


@pytest.fixture
def _real_bridge_over_synthetic_corpus(tmp_path, monkeypatch):
    """Point the real ``agenticrag.relationships`` bridge at a tiny synthetic
    ``candidates.jsonl`` (real linkgraph loader + graph, no corpus/Qdrant) and
    reset its process-wide graph cache so the fixture graph is the one built."""
    from agenticrag import relationships

    path = tmp_path / "candidates.jsonl"
    path.write_text(
        "\n".join(json.dumps(obj) for obj in _SYNTHETIC_CANDIDATES) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(relationships, "_DEFAULT_CANDIDATES_PATH", path)
    monkeypatch.setattr(relationships, "_GRAPH", None)  # rebuild against the fixture
    yield
    # monkeypatch restores _GRAPH to None on teardown; the next real caller rebuilds.


def test_get_corrections_success_returns_ok_envelope(_real_bridge_over_synthetic_corpus):
    out = server.tool_get_corrections("RFC2616")
    assert out["ok"] is True, out
    assert out["tool"] == "get_corrections", out
    assert out["result"] == ["100"], out  # the one Verified erratum's bare id


def test_get_related_success_returns_ok_envelope(_real_bridge_over_synthetic_corpus):
    out = server.tool_get_related("rfc:RFC2616", max_hops=1)
    assert out["ok"] is True, out
    assert out["tool"] == "get_related", out
    assert isinstance(out["result"], list), out
    reached = {node for node, _hop in out["result"]}
    assert "rfc:7230" in reached, out      # obsoletion neighbour (numeric target id)
    assert "errata:100" in reached, out    # corrects neighbour


def test_get_obsoletion_chain_success_returns_ok_envelope(_real_bridge_over_synthetic_corpus):
    out = server.tool_get_obsoletion_chain("RFC2616")
    assert out["ok"] is True, out
    assert out["tool"] == "get_obsoletion_chain", out
    assert isinstance(out["result"], dict), out
    assert "history" in out["result"], out


if __name__ == "__main__":
    import json
    import traceback

    cases = [
        check_search_abstain,
        check_search_healthy_compute,
        check_get_related_fallback,
        check_get_obsoletion_chain_fallback,
        check_get_corrections_fallback,
    ]
    failures = 0
    for case in cases:
        try:
            result = case()
            print(f"PASS  {case.__name__}")
            print(f"      -> {json.dumps(result, default=str)}")
        except Exception:
            failures += 1
            print(f"FAIL  {case.__name__}")
            traceback.print_exc()
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    sys.exit(1 if failures else 0)
