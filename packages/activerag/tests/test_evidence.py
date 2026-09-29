"""Tests for activerag.evidence.

Built entirely against hand-constructed fixture ``Answer``/``RouteResult``
objects: no Consilium instantiation, no embedder, no real modules. The
fixtures below mirror the real ``consilium.composer.Answer`` /
``consilium.router.RouteResult`` field shapes (see
``packages/consilium/consilium/{composer.py,router.py}``) but are plain local
dataclasses, matching ``activerag.evidence``'s structural (``Protocol``-based)
contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from activerag.evidence import evaluate


@dataclass
class FakeCitation:
    claim: str
    module: str = "mod_a"
    doc: str = "doc1"
    chunk_id: str = "c1"
    score: float = 0.9


@dataclass
class FakeAnswer:
    query: str = "q"
    text: str = "text"
    citations: list = field(default_factory=list)
    modules_used: list = field(default_factory=list)
    abstained: bool = False
    dropped: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    quarantined: list = field(default_factory=list)


@dataclass
class FakeRouteResult:
    query: str = "q"
    ranked: list = field(default_factory=list)
    selected: list = field(default_factory=list)
    abstained: bool = False
    trace: dict = field(default_factory=dict)


def _healthy_answer_and_route():
    citations = [FakeCitation("claim1"), FakeCitation("claim2"), FakeCitation("claim3")]
    answer = FakeAnswer(citations=citations, dropped=["dropped1"], abstained=False)
    route = FakeRouteResult(
        ranked=[("mod_a", 0.5, {}), ("mod_b", 0.2, {})],
        abstained=False,
        trace={"floor": 0.11, "top": 0.5},
    )
    return answer, route


def test_abstained_answer_is_always_insufficient_regardless_of_other_fields():
    # Plenty of citations, no drops, huge margin, but abstained=True must
    # override all three numeric checks.
    citations = [FakeCitation("c1"), FakeCitation("c2"), FakeCitation("c3")]
    answer = FakeAnswer(citations=citations, dropped=[], abstained=True)
    route = FakeRouteResult(ranked=[("m", 0.9, {})], abstained=False, trace={"floor": 0.11})

    verdict = evaluate(answer, route)

    assert verdict.sufficient is False
    assert verdict.reason == "abstained"


def test_route_result_abstained_also_forces_insufficient():
    # Only route_result.abstained is set (answer.abstained left False) --
    # either flag must be enough to short-circuit to "abstained".
    citations = [FakeCitation("c1"), FakeCitation("c2"), FakeCitation("c3")]
    answer = FakeAnswer(citations=citations, dropped=[], abstained=False)
    route = FakeRouteResult(
        ranked=[], abstained=True, trace={"reason": "no module cleared floor", "floor": 0.11}
    )

    verdict = evaluate(answer, route)

    assert verdict.sufficient is False
    assert verdict.reason == "abstained"


def test_below_min_citations_is_insufficient_with_distinguishing_reason():
    answer = FakeAnswer(citations=[FakeCitation("only_one")], dropped=[], abstained=False)
    route = FakeRouteResult(ranked=[("m", 0.5, {})], abstained=False, trace={"floor": 0.11})

    verdict = evaluate(answer, route)

    assert verdict.sufficient is False
    assert verdict.reason == "too_few_citations"
    assert verdict.citation_count == 1


def test_high_dropped_ratio_is_insufficient_with_distinguishing_reason():
    citations = [FakeCitation("c1"), FakeCitation("c2")]
    dropped = ["d1", "d2", "d3"]  # 3 / (2 + 3) = 0.6 > MAX_DROPPED_RATIO (0.5)
    answer = FakeAnswer(citations=citations, dropped=dropped, abstained=False)
    route = FakeRouteResult(ranked=[("m", 0.5, {})], abstained=False, trace={"floor": 0.11})

    verdict = evaluate(answer, route)

    assert verdict.sufficient is False
    assert verdict.reason == "high_dropped_ratio"
    assert verdict.dropped_ratio == 0.6


def test_thin_margin_is_insufficient_with_distinguishing_reason():
    citations = [FakeCitation("c1"), FakeCitation("c2")]
    answer = FakeAnswer(citations=citations, dropped=[], abstained=False)
    # top score 0.12, floor 0.11 -> margin 0.01 < MARGIN_FLOOR (0.03)
    route = FakeRouteResult(ranked=[("m", 0.12, {})], abstained=False, trace={"floor": 0.11})

    verdict = evaluate(answer, route)

    assert verdict.sufficient is False
    assert verdict.reason == "thin_margin"
    assert round(verdict.top_margin, 2) == 0.01


def test_reasons_are_distinguishable_across_all_four_failure_modes():
    # A single set comprehension proves every failure mode produces a unique,
    # separately-identifiable reason string.
    abstained_answer = FakeAnswer(citations=[FakeCitation("c1")] * 3, abstained=True)
    abstained_route = FakeRouteResult(ranked=[("m", 0.9, {})], trace={"floor": 0.11})

    few_citations_answer = FakeAnswer(citations=[FakeCitation("only_one")])
    few_citations_route = FakeRouteResult(ranked=[("m", 0.5, {})], trace={"floor": 0.11})

    high_dropped_answer = FakeAnswer(
        citations=[FakeCitation("c1"), FakeCitation("c2")], dropped=["d1", "d2", "d3"]
    )
    high_dropped_route = FakeRouteResult(ranked=[("m", 0.5, {})], trace={"floor": 0.11})

    thin_margin_answer = FakeAnswer(citations=[FakeCitation("c1"), FakeCitation("c2")])
    thin_margin_route = FakeRouteResult(ranked=[("m", 0.12, {})], trace={"floor": 0.11})

    reasons = {
        evaluate(abstained_answer, abstained_route).reason,
        evaluate(few_citations_answer, few_citations_route).reason,
        evaluate(high_dropped_answer, high_dropped_route).reason,
        evaluate(thin_margin_answer, thin_margin_route).reason,
    }
    assert reasons == {"abstained", "too_few_citations", "high_dropped_ratio", "thin_margin"}


def test_normal_well_cited_answer_with_comfortable_margin_is_sufficient():
    answer, route = _healthy_answer_and_route()

    verdict = evaluate(answer, route)

    assert verdict.sufficient is True
    assert verdict.reason == "sufficient"


def test_healthy_looking_answer_does_not_trigger_false_positive_hunt():
    """Guards against an overly aggressive default: a realistic, healthy
    answer (several citations, a low-but-nonzero dropped ratio, a solid
    margin over the router floor) must NOT be flagged as needing a hunt."""
    citations = [FakeCitation(f"claim{i}") for i in range(5)]
    answer = FakeAnswer(citations=citations, dropped=["one_bad_claim"], abstained=False)
    route = FakeRouteResult(
        ranked=[("primary", 0.42, {}), ("secondary", 0.15, {})],
        abstained=False,
        trace={"floor": 0.11, "top": 0.42},
    )

    verdict = evaluate(answer, route)

    assert verdict.sufficient is True
    assert verdict.reason == "sufficient"
