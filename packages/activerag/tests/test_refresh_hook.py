"""Tests for activerag.refresh_hook.make_refresh_and_research.

Hermetic: RegistryBridge is driven by a FakeBuildRegistry (as in
test_registry_bridge.py), and run_ingest_fn/route_and_compose_fn are injected
fakes: no real Qdrant, embedder, ingest pipeline, or consilium Router/compose
is ever touched. Proves call order and data flow only.
"""
from __future__ import annotations

from pathlib import Path

from activerag.evidence import EvidenceVerdict
from activerag.refresh_hook import make_refresh_and_research
from activerag.registry_bridge import RegistryBridge


class FakeRegistry:
    def __init__(self, build_id):
        self.build_id = build_id


class FakeBuildRegistry:
    def __init__(self):
        self._next_id = 0

    def __call__(self, embedder, client=None):
        self._next_id += 1
        return FakeRegistry(self._next_id)


class FakeAnswer:
    citations = ["c1", "c2"]
    dropped = []
    abstained = False


class FakeRouteResult:
    ranked = [("rfc_text", 0.9, {})]
    abstained = False
    trace = {"floor": 0.3}


def _make_bridge():
    return RegistryBridge(embedder=object(), build_registry=FakeBuildRegistry())


def test_copies_found_docs_into_the_source_types_raw_dir(tmp_path):
    bridge = _make_bridge()
    src = tmp_path / "staging"
    src.mkdir()
    doc = src / "rfc9999.txt"
    doc.write_text("hello")

    ingest_calls = []
    route_calls = []

    def fake_run_ingest(data_dir):
        ingest_calls.append(data_dir)

    def fake_route_and_compose(query, registry, embedder, router_kwargs):
        route_calls.append((query, registry, embedder, router_kwargs))
        return FakeAnswer(), FakeRouteResult()

    hook = make_refresh_and_research(
        bridge, embedder=object(), router_kwargs={"floor": 0.3},
        agentic_rag_root=tmp_path / "agentic-rag",
        run_ingest_fn=fake_run_ingest,
        route_and_compose_fn=fake_route_and_compose,
    )

    verdict = hook("what obsoleted RFC2616?", "rfc_text", [doc])

    copied = tmp_path / "agentic-rag" / "data" / "raw" / "rfc_text" / "rfc9999.txt"
    assert copied.read_text() == "hello"
    assert isinstance(verdict, EvidenceVerdict)


def test_calls_ingest_then_refresh_then_route_and_compose_in_order(tmp_path):
    bridge = _make_bridge()
    order = []

    def fake_run_ingest(data_dir):
        order.append("ingest")

    def fake_route_and_compose(query, registry, embedder, router_kwargs):
        order.append("route_and_compose")
        assert registry.build_id == 2  # the POST-refresh registry, not the initial one
        return FakeAnswer(), FakeRouteResult()

    real_refresh_all = bridge.refresh_all

    def spying_refresh_all():
        order.append("refresh_all")
        return real_refresh_all()

    bridge.refresh_all = spying_refresh_all

    hook = make_refresh_and_research(
        bridge, embedder=object(), router_kwargs={},
        agentic_rag_root=tmp_path / "agentic-rag",
        run_ingest_fn=fake_run_ingest,
        route_and_compose_fn=fake_route_and_compose,
    )
    hook("q", "rfc_text", [])

    assert order == ["ingest", "refresh_all", "route_and_compose"]


def test_returns_the_real_evaluate_evidence_verdict_for_the_composed_answer(tmp_path):
    bridge = _make_bridge()

    def fake_route_and_compose(query, registry, embedder, router_kwargs):
        return FakeAnswer(), FakeRouteResult()

    hook = make_refresh_and_research(
        bridge, embedder=object(), router_kwargs={},
        agentic_rag_root=tmp_path / "agentic-rag",
        run_ingest_fn=lambda data_dir: None,
        route_and_compose_fn=fake_route_and_compose,
    )
    verdict = hook("q", "rfc_text", [])

    # FakeAnswer/FakeRouteResult clear every evidence.evaluate bar, so sufficient.
    assert verdict.sufficient is True
    assert verdict.citation_count == 2


def test_no_found_docs_still_ingests_refreshes_and_reanswers(tmp_path):
    bridge = _make_bridge()
    calls = []

    hook = make_refresh_and_research(
        bridge, embedder=object(), router_kwargs={},
        agentic_rag_root=tmp_path / "agentic-rag",
        run_ingest_fn=lambda data_dir: calls.append("ingest"),
        route_and_compose_fn=lambda *a: (calls.append("answer"), (FakeAnswer(), FakeRouteResult()))[1],
    )
    hook("q", "rfc_text", [])

    assert calls == ["ingest", "answer"]
    raw_dir = tmp_path / "agentic-rag" / "data" / "raw" / "rfc_text"
    assert raw_dir.is_dir() and list(raw_dir.iterdir()) == []
