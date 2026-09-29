"""Detect thin evidence in a set of search hits, so a caller can decide whether to hunt for more.

This is a pure, domain-agnostic check: it knows nothing about documents, chunks, or where hits
came from: just their scores and count. ``min_top_score``'s default (0.15) is a conservative,
uncalibrated placeholder; real callers should calibrate it against their own embedder + corpus
before trusting it, the same lesson chain-rag's README documents about Consilium's Router
defaults: a near-zero-baseline assumption for raw cosine similarity is often wrong for real
dense embedders, and floors need per-corpus calibration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import Hit


@dataclass
class EvidenceVerdict:
    sufficient: bool
    reason: str
    hit_count: int
    top_score: float


def evaluate_evidence(hits: list[Hit], *, min_hits: int = 1, min_top_score: float = 0.15) -> EvidenceVerdict:
    """Judge whether ``hits`` clears a minimum bar of count + top-score confidence."""
    hit_count = len(hits)
    top_score = hits[0].score if hits else 0.0

    if hit_count < min_hits:
        return EvidenceVerdict(
            sufficient=False,
            reason=f"only {hit_count} hit(s), need at least {min_hits}",
            hit_count=hit_count,
            top_score=top_score,
        )
    if top_score < min_top_score:
        return EvidenceVerdict(
            sufficient=False,
            reason=f"top score {top_score:.3f} is below the {min_top_score:.3f} floor",
            hit_count=hit_count,
            top_score=top_score,
        )
    return EvidenceVerdict(sufficient=True, reason="sufficient", hit_count=hit_count, top_score=top_score)
