"""Pure unit tests of evaluate_evidence -- no Qdrant, no embedder, no I/O."""
from ragpack import EvidenceVerdict, Hit, evaluate_evidence


def _hit(score: float, source: str = "doc.md") -> Hit:
    return Hit(score=score, text="some text", source=source, payload={})


def test_empty_hits_is_insufficient():
    verdict = evaluate_evidence([])
    assert verdict.sufficient is False
    assert verdict.hit_count == 0
    assert verdict.top_score == 0.0


def test_below_min_hits_is_insufficient():
    verdict = evaluate_evidence([_hit(0.9)], min_hits=2)
    assert verdict.sufficient is False
    assert verdict.hit_count == 1


def test_meets_min_hits_but_low_top_score_is_insufficient():
    verdict = evaluate_evidence([_hit(0.05), _hit(0.04)], min_hits=1, min_top_score=0.15)
    assert verdict.sufficient is False
    assert verdict.hit_count == 2
    assert verdict.top_score == 0.05


def test_clears_both_checks_is_sufficient():
    verdict = evaluate_evidence([_hit(0.42), _hit(0.3)], min_hits=1, min_top_score=0.15)
    assert verdict.sufficient is True
    assert verdict.reason == "sufficient"


def test_reasons_distinguish_the_two_failure_modes():
    too_few = evaluate_evidence([], min_hits=1)
    too_weak = evaluate_evidence([_hit(0.01)], min_hits=1, min_top_score=0.15)
    assert too_few.reason and too_weak.reason
    assert too_few.reason != too_weak.reason


def test_verdict_is_a_plain_dataclass():
    verdict = evaluate_evidence([_hit(0.5)])
    assert isinstance(verdict, EvidenceVerdict)
