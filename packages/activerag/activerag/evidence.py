"""Detect when a Consilium ``Answer`` is resting on evidence too thin to trust,
so a caller can decide whether to hunt for more sources before finalizing it.

This is the Consilium-aware sibling of RAGpack's own evidence check
(``ragpack.evidence.evaluate_evidence`` in
``packages/ragpack/src/ragpack/evidence.py``), which judges a flat list of
``Hit`` objects by count + top score alone, before any citation gate has run.
By the time a query has become a Consilium ``Answer``, it has already passed
through the router (``consilium.router.Router``) and the integrity gate
(``consilium.integrity.gate``), so richer signals are available: which claims
actually survived the gate (citations), which were thrown out
(``Answer.dropped``), and how comfortably the router cleared its own abstain
floor (``RouteResult.trace["floor"]``). This module reads those
already-computed signals instead of re-deriving a hit list, the same
"detect thin evidence, hunt for more" spirit as RAGpack's primitive, one level
higher up the stack, closer to what would actually ship in a final answer.

Three independent checks; any one failing is enough to call the evidence
insufficient. A false "sufficient" ships a possibly-wrong answer with no
second chance, while a false "insufficient" costs only one extra hunt, so the
check errs toward caution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# An answer resting on a single citation is one bad chunk away from being
# silently wrong: there is no corroboration. Two is the minimum bar for
# "more than one independent thing agrees with this."
MIN_CITATIONS = 2

# If over half of the raw retrieved claims failed the integrity gate, the raw
# retrieval was already thin before hardening ran. The survivors are the
# exception, not the rule, even if there happen to be enough of them.
MAX_DROPPED_RATIO = 0.5

# A razor-thin margin over the router's own abstain floor means the router
# almost didn't return anything at all; the selection is a coin-flip away
# from having abstained outright.
MARGIN_FLOOR = 0.03


@runtime_checkable
class AnswerLike(Protocol):
    """Structural contract for a Consilium ``Answer`` (see
    ``consilium.composer.Answer``).

    A ``Protocol`` rather than an import of the real dataclass, since this
    module never needs to import consilium at runtime: a test can hand it
    any object (a real ``Answer``, a hand-built fixture, a plain namespace)
    exposing these three attributes.
    """

    citations: list
    dropped: list
    abstained: bool


@runtime_checkable
class RouteResultLike(Protocol):
    """Structural contract for a Consilium ``RouteResult`` (see
    ``consilium.router.RouteResult``)."""

    ranked: list
    abstained: bool
    trace: dict


@dataclass
class EvidenceVerdict:
    sufficient: bool
    reason: str
    citation_count: int
    dropped_ratio: float
    top_margin: float


def evaluate(
    answer: AnswerLike,
    route_result: RouteResultLike,
    *,
    min_citations: int = MIN_CITATIONS,
    max_dropped_ratio: float = MAX_DROPPED_RATIO,
    margin_floor: float = MARGIN_FLOOR,
) -> EvidenceVerdict:
    """Judge whether ``answer`` (routed via ``route_result``) clears a minimum
    bar of citation count, integrity-gate survival rate, and router margin.

    An explicitly abstained answer, either ``answer.abstained`` or
    ``route_result.abstained`` (Consilium sets both together, but both are
    checked so this function is robust to a caller that only has one), is
    always insufficient, independent of the three numeric checks: there is no
    evidence to score in the first place.
    """
    citation_count = len(answer.citations)
    total_claims = citation_count + len(answer.dropped)
    dropped_ratio = (len(answer.dropped) / total_claims) if total_claims else 0.0

    if route_result.ranked:
        top_score = route_result.ranked[0][1]
        floor = route_result.trace.get("floor", 0.0)
        top_margin = top_score - floor
    else:
        top_margin = 0.0

    if answer.abstained or route_result.abstained:
        return EvidenceVerdict(
            sufficient=False,
            reason="abstained",
            citation_count=citation_count,
            dropped_ratio=dropped_ratio,
            top_margin=top_margin,
        )

    failed_checks = []
    if citation_count < min_citations:
        failed_checks.append("too_few_citations")
    if dropped_ratio > max_dropped_ratio:
        failed_checks.append("high_dropped_ratio")
    if top_margin < margin_floor:
        failed_checks.append("thin_margin")

    reason = "+".join(failed_checks) if failed_checks else "sufficient"
    return EvidenceVerdict(
        sufficient=not failed_checks,
        reason=reason,
        citation_count=citation_count,
        dropped_ratio=dropped_ratio,
        top_margin=top_margin,
    )
