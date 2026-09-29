"""Tests for activerag.orchestrator.

Hermetic: the whole hunt cycle is driven by hand-built fakes: fake
``Answer``/``RouteResult`` fixtures (same field shapes as ``test_evidence``),
fake zero-arg ``hunt_fn`` callables, a fake ``refresh_and_research`` hook, and a
fake headroom ``gate``, so no live registry, Qdrant, embedder, GPU, or network
is touched. Telemetry is written to a real ``tmp_path`` JSONL and read back,
matching the no-live-dependency style of the other activerag tests.

The real ``HuntDecision``/``Decision`` are reused (they are pure dataclass/enum,
no hardware) so the gate fakes produce exactly the objects the orchestrator will
see in production.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

# `orchestrator` itself does not import `headroom_gate` (see the note at
# orchestrator.py:80); only this test does, for the real Decision/HuntDecision. Skip rather
# than fail collection so a missing sibling repo does not abort the entire suite.
pytest.importorskip(
    "activerag.headroom_gate",
    reason="needs the sibling rag-reliability/headroom module on sys.path",
)

from activerag.evidence import EvidenceVerdict  # noqa: E402
from activerag.headroom_gate import Decision, HuntDecision  # noqa: E402
from activerag.orchestrator import run_hunt_cycle  # noqa: E402
from activerag.telemetry import read_events  # noqa: E402


# --- fixtures mirroring consilium.composer.Answer / consilium.router.RouteResult
@dataclass
class FakeCitation:
    claim: str
    score: float = 0.9


@dataclass
class FakeAnswer:
    query: str = "q"
    text: str = "text"
    citations: list = field(default_factory=list)
    abstained: bool = False
    dropped: list = field(default_factory=list)


@dataclass
class FakeRouteResult:
    query: str = "q"
    ranked: list = field(default_factory=list)
    abstained: bool = False
    trace: dict = field(default_factory=dict)


def _insufficient_answer_and_route():
    # One citation is below MIN_CITATIONS (2), so evidence.evaluate says
    # insufficient ("too_few_citations"), which triggers the hunt cycle.
    answer = FakeAnswer(citations=[FakeCitation("c1")], dropped=[], abstained=False)
    route = FakeRouteResult(
        ranked=[("m", 0.5, {})], abstained=False, trace={"floor": 0.11}
    )
    return answer, route


def _sufficient_answer_and_route():
    citations = [FakeCitation("c1"), FakeCitation("c2"), FakeCitation("c3")]
    answer = FakeAnswer(citations=citations, dropped=["d1"], abstained=False)
    route = FakeRouteResult(
        ranked=[("m", 0.5, {})], abstained=False, trace={"floor": 0.11}
    )
    return answer, route


# --- verdict + hook + gate + hunt fakes ---------------------------------------
def _verdict(sufficient: bool, reason: str = "r") -> EvidenceVerdict:
    return EvidenceVerdict(
        sufficient=sufficient,
        reason=reason,
        citation_count=3 if sufficient else 1,
        dropped_ratio=0.0,
        top_margin=0.4,
    )


def _allow_gate(candidate) -> HuntDecision:
    return HuntDecision(may_hunt=True, decision=Decision.ALLOW, reason="ok", hops_observed=0)


def _deny_gate(candidate) -> HuntDecision:
    return HuntDecision(
        may_hunt=False, decision=Decision.DENY, reason="vram ceiling", hops_observed=3
    )


class RecordingHunt:
    """A zero-arg hunt_fn (StagingDirHuntSource-shaped) that returns a fixed list
    of fake paths and counts how many times it was called."""

    def __init__(self, names):
        self._paths = [Path(n) for n in names]
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return list(self._paths)


class RecordingRefresh:
    """A fake refresh_and_research hook. ``verdict_for`` maps a source_type to the
    EvidenceVerdict that source's re-search should yield; unlisted types default
    to still-insufficient. Records every (query, source_type, docs) call."""

    def __init__(self, verdict_for):
        self._verdict_for = verdict_for
        self.calls = []

    def __call__(self, query, source_type, found_docs) -> EvidenceVerdict:
        self.calls.append((query, source_type, list(found_docs)))
        return self._verdict_for.get(source_type, _verdict(False, "still_thin"))


def _boom(*_a, **_k):  # a callable that must never be invoked in a given test
    raise AssertionError("must not be called")


# --- tests --------------------------------------------------------------------
def test_sufficient_evidence_short_circuits_with_zero_hunts(tmp_path):
    answer, route = _sufficient_answer_and_route()
    path = tmp_path / "hunts.jsonl"

    result = run_hunt_cycle(
        query="q",
        answer=answer,
        route_result=route,
        entity_hints=[],
        known_source_types=["a", "b"],
        hunt_sources={"a": _boom, "b": _boom},   # must never be hunted
        refresh_and_research=_boom,              # must never be researched
        gate=_boom,                              # must never be gated
        telemetry_path=path,
    )

    assert result.initial_verdict.sufficient is True
    assert result.hunted is False
    assert result.resolved is False
    assert result.winning_source is None
    assert result.attempts == []
    assert result.event is None
    # No hunt cycle ran, so nothing was appended to the trail.
    assert read_events(path) == []


def test_bounded_loop_never_exceeds_candidate_count(tmp_path):
    # Every source finds docs but re-search never improves the verdict: the loop
    # must try each candidate EXACTLY once and then stop (capped), never loop.
    answer, route = _insufficient_answer_and_route()
    path = tmp_path / "hunts.jsonl"
    known = ["a", "b", "c"]
    hunts = {s: RecordingHunt([f"{s}.md"]) for s in known}
    refresh = RecordingRefresh({})  # everything stays insufficient

    result = run_hunt_cycle(
        query="q",
        answer=answer,
        route_result=route,
        entity_hints=[],
        known_source_types=known,
        hunt_sources=hunts,
        refresh_and_research=refresh,
        gate=_allow_gate,
        telemetry_path=path,
    )

    # Exactly one attempt per candidate, in priority (== caller) order, no dupes.
    assert [a.source_type for a in result.attempts] == known
    assert len(result.attempts) == len(known)
    assert len({a.source_type for a in result.attempts}) == len(known)
    # Each hunt_fn and the refresh hook were each invoked exactly once per source.
    assert all(h.calls == 1 for h in hunts.values())
    assert [c[1] for c in refresh.calls] == known
    # Unresolved after exhausting all candidates: capped, no winner.
    assert result.resolved is False
    assert result.winning_source is None
    assert result.hunted is True
    assert result.event.capped is True


def test_gate_denial_skips_that_hunt_attempt(tmp_path):
    # Deny the first candidate, allow the rest. The denied candidate's hunt_fn
    # must NOT run; the next candidate resolves the cycle.
    answer, route = _insufficient_answer_and_route()
    path = tmp_path / "hunts.jsonl"
    known = ["a", "b"]
    hunt_a = RecordingHunt(["a.md"])
    hunt_b = RecordingHunt(["b.md"])
    refresh = RecordingRefresh({"b": _verdict(True, "sufficient")})

    def selective_gate(candidate) -> HuntDecision:
        return _deny_gate(candidate) if candidate.source_type == "a" else _allow_gate(candidate)

    result = run_hunt_cycle(
        query="q",
        answer=answer,
        route_result=route,
        entity_hints=[],
        known_source_types=known,
        hunt_sources={"a": hunt_a, "b": hunt_b},
        refresh_and_research=refresh,
        gate=selective_gate,
        telemetry_path=path,
    )

    # 'a' was gated out: recorded, not hunted, hunt_fn never called.
    a_rec = result.attempts[0]
    assert a_rec.source_type == "a"
    assert a_rec.hunted is False
    assert a_rec.reason.startswith("gated_")
    assert hunt_a.calls == 0
    # 'b' passed the gate, was hunted, and resolved the cycle.
    assert hunt_b.calls == 1
    assert result.winning_source == "b"
    assert result.resolved is True
    # refresh was only ever consulted for the un-gated source.
    assert [c[1] for c in refresh.calls] == ["b"]


def test_second_candidate_succeeds_after_first_fails(tmp_path):
    # 'a' hunts + ingests but stays insufficient; 'b' hunts + ingests and becomes
    # sufficient, so the cycle stops at 'b'; 'c' is never reached (bounded, first-win).
    answer, route = _insufficient_answer_and_route()
    path = tmp_path / "hunts.jsonl"
    known = ["a", "b", "c"]
    hunt_a = RecordingHunt(["a1.md"])
    hunt_b = RecordingHunt(["b1.md", "b2.md"])
    hunt_c = RecordingHunt(["c1.md"])
    refresh = RecordingRefresh({"b": _verdict(True, "sufficient")})  # 'a': insufficient

    result = run_hunt_cycle(
        query="q",
        answer=answer,
        route_result=route,
        entity_hints=[],
        known_source_types=known,
        hunt_sources={"a": hunt_a, "b": hunt_b, "c": hunt_c},
        refresh_and_research=refresh,
        gate=_allow_gate,
        telemetry_path=path,
    )

    assert [a.source_type for a in result.attempts] == ["a", "b"]  # stopped before 'c'
    assert result.attempts[0].reason.startswith("still_insufficient_")
    assert result.attempts[1].reason == "sufficient_after_hunt"
    assert result.winning_source == "b"
    assert result.resolved is True
    assert result.final_verdict.sufficient is True
    assert result.docs_ingested == 3  # 1 from 'a' + 2 from 'b', both ingested
    # 'c' was never touched: the cycle is bounded and stops on first success.
    assert hunt_c.calls == 0
    assert "c" not in [c[1] for c in refresh.calls]
    assert result.event.capped is False  # resolved, not exhausted


def test_telemetry_records_every_attempt(tmp_path):
    # A mixed cycle: no-source, gated-out, found-nothing, then a resolving hunt;
    # every one must land in the single appended event's sources_tried.
    answer, route = _insufficient_answer_and_route()
    path = tmp_path / "hunts.jsonl"
    known = ["missing", "denied", "empty", "winner"]
    hunts = {
        # 'missing' intentionally has NO hunt source registered.
        "denied": RecordingHunt(["d.md"]),
        "empty": RecordingHunt([]),          # hunts, finds nothing
        "winner": RecordingHunt(["w.md"]),
    }
    refresh = RecordingRefresh({"winner": _verdict(True, "sufficient")})

    def gate(candidate) -> HuntDecision:
        return _deny_gate(candidate) if candidate.source_type == "denied" else _allow_gate(candidate)

    result = run_hunt_cycle(
        query="q",
        answer=answer,
        route_result=route,
        entity_hints=[],
        known_source_types=known,
        hunt_sources=hunts,
        refresh_and_research=refresh,
        gate=gate,
        telemetry_path=path,
    )

    # Exactly ONE event was appended for this cycle.
    events = read_events(path)
    assert len(events) == 1
    event = events[0]

    # Every candidate up to and including the winner is recorded, in order, once.
    tried = event["sources_tried"]
    assert [s["source_type"] for s in tried] == ["missing", "denied", "empty", "winner"]
    reason_by_type = {s["source_type"]: s["reason"] for s in tried}
    assert reason_by_type["missing"] == "no_hunt_source"
    assert reason_by_type["denied"].startswith("gated_")
    assert reason_by_type["empty"] == "found_nothing"
    assert reason_by_type["winner"] == "sufficient_after_hunt"

    # hunted flags: only the two that actually ran hunt_fn are hunted=True.
    hunted_by_type = {s["source_type"]: s["hunted"] for s in tried}
    assert hunted_by_type == {
        "missing": False,
        "denied": False,
        "empty": True,
        "winner": True,
    }

    # Cycle-level fields captured on the same event.
    assert event["winning_source"] == "winner"
    assert event["capped"] is False
    assert event["docs_ingested"] == 1
    assert event["initial_verdict"]["sufficient"] is False
    assert event["final_verdict"]["sufficient"] is True
    # The returned event mirrors exactly what was persisted.
    assert result.event.winning_source == "winner"
    assert result.winning_source == "winner"


def test_all_sources_gated_out_records_no_hunts_but_still_writes_event(tmp_path):
    # If the hardware denies every candidate, no hunt_fn runs, but the cycle is
    # still audited (capped, hunted=False) so the refusal is replayable.
    answer, route = _insufficient_answer_and_route()
    path = tmp_path / "hunts.jsonl"
    hunt_a = RecordingHunt(["a.md"])

    result = run_hunt_cycle(
        query="q",
        answer=answer,
        route_result=route,
        entity_hints=[],
        known_source_types=["a"],
        hunt_sources={"a": hunt_a},
        refresh_and_research=_boom,   # never reached: gate blocks first
        gate=_deny_gate,
        telemetry_path=path,
    )

    assert hunt_a.calls == 0
    assert result.hunted is False
    assert result.resolved is False
    assert result.event.capped is True
    assert len(read_events(path)) == 1
