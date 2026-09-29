"""Cheap, explainable source ordering for a hunt-and-retry cycle.

When :mod:`activerag.evidence` flags an answer as insufficiently supported,
something has to decide which source to hunt in first. RAGpack's own
``RAGpack.ingest_and_retry`` (``packages/ragpack/src/ragpack/pipeline.py``)
leaves that decision entirely to the caller's ``hunt_fn``; it is a single,
undifferentiated hunt. At the Consilium layer there is usually more than one
candidate source (multiple local registries plus a last-resort internet
fetch), so something has to rank them before the orchestrator
(:mod:`activerag.orchestrator`) tries them in order.

This module is not a learned ranker: there is no training data for "which
source resolves a hunt fastest" yet, so it uses an explainable heuristic
instead of a black box with nothing to justify it.

The exact rule (so a reader can predict the ordering without running the
code):

1. ``entity_hints`` is taken to already be a list of ``known_source_types``
   values, supplied by the caller in the caller's own preference order,
   i.e. "the source types that structurally reference the kind of entity this
   query is about, ranked by how directly they reference it." (Extracting
   those hints from raw query text is the caller's job, upstream of this
   function; ``query`` is accepted for API stability / future use but the v1
   heuristic does not re-parse it.)
2. Every hinted source type that also appears in ``known_source_types`` is
   placed first, in hint order, deduplicated (first occurrence wins).
3. Every remaining known source type (not hinted) is appended next, in the
   order ``known_source_types`` was given; the caller is assumed to have
   already listed its locally-known sources in its own sane default order.
4. The pseudo-source-type ``"internet"``, if present in ``known_source_types``,
   is always moved to the very end, even if it was hinted. Internet is the
   last resort, reached only once every real local source has been tried and
   failed (a later orchestrator task enforces that "only reached last"
   behavior at call time; this function only guarantees it never outranks a
   real source).
"""
from __future__ import annotations

from dataclasses import dataclass

INTERNET_SOURCE_TYPE = "internet"


@dataclass
class SourceCandidate:
    source_type: str
    priority_rank: int


def rank_sources(
    query: str,
    entity_hints: list[str],
    known_source_types: list[str],
) -> list[SourceCandidate]:
    """Order ``known_source_types`` by hint match, falling back to caller
    order, with ``"internet"`` always sorted last. See the module docstring
    for the exact rule. ``query`` is currently unused by the heuristic (see
    docstring) but kept in the signature for API stability."""
    del query  # not used by the v1 heuristic; see module docstring

    known_deduped = list(dict.fromkeys(known_source_types))
    has_internet = INTERNET_SOURCE_TYPE in known_deduped

    hinted = [
        h for h in dict.fromkeys(entity_hints)
        if h in known_deduped and h != INTERNET_SOURCE_TYPE
    ]
    rest = [s for s in known_deduped if s not in hinted and s != INTERNET_SOURCE_TYPE]

    ordered = hinted + rest
    if has_internet:
        ordered.append(INTERNET_SOURCE_TYPE)

    return [
        SourceCandidate(source_type=source_type, priority_rank=rank)
        for rank, source_type in enumerate(ordered, start=1)
    ]
