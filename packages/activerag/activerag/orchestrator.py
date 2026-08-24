"""The glue: one BOUNDED hunt-and-retry cycle over a Consilium answer.

When :mod:`activerag.evidence` flags an existing ``Answer`` as resting on thin
evidence, *something* has to actually do the hunting: pick which sources to try
(``priority``), ask the hardware whether there is physical room to try them
(``headroom_gate``), attempt each hunt (a ``hunt``-shaped ``hunt_fn``), re-search
after ingesting whatever was found, and leave a durable audit trail
(``telemetry``). This module is that conductor. Every other activerag module is a
single-purpose instrument; this one plays them in order and stops on time.

Intentional, documented departure from RAGpack
-----------------------------------------------
RAGpack's ``RAGpack.ingest_and_retry``
(``projects/RAGpack/src/ragpack/pipeline.py``) is deliberately a *single* hunt:
"if the evidence is thin, ask ONE ``hunt_fn`` for more content, ingest it, and
search once more. Never retries a second time -- this is a single hunt-and-retry,
not a loop." That is the right contract for a flat corpus with one undifferentiated
source.

At the Consilium layer there is usually more than one candidate source (several
local registries plus a last-resort internet fetch), so this module GENERALIZES
that contract -- **on purpose, not by oversight** -- into: "try multiple
*different source-typed* hunts, in priority order, within ONE bounded cycle."
The generalization keeps RAGpack's core safety promise (a cycle always
terminates; work is never repeated) while widening the single hunt into a ranked
sweep:

* **Bounded.** The cycle iterates the ranked candidate list at most once. It stops
  at the FIRST hunt that improves the verdict to sufficient, or when the candidate
  list is exhausted -- whichever comes first. It can never run longer than there
  are candidates.
* **No candidate twice.** ``priority.rank_sources`` de-duplicates source types and
  the loop visits each exactly once; a single candidate is never re-hunted within
  a cycle. (RAGpack's "never loops twice" promise, lifted from one source to N.)
* **Every attempt recorded.** Attempted, gated-out (headroom said no), found-
  nothing, still-insufficient, and succeeded are ALL written to the telemetry
  trail, so the sweep is fully replayable after the fact.

Injection point for the real registry (kept injected so this module owns control
flow only)
----------------------------------------------------------------------------------
The re-search/re-ingest step is the ONLY part that needs a live embedder + Qdrant
+ the agentic-rag registry. Rather than importing that machinery here and
hard-coupling this module to it, that dependency is INJECTED as the
``refresh_and_research`` callable:

    ``refresh_and_research(query, source_type, found_docs) -> EvidenceVerdict``

Given the query, the source type just hunted, and the freshly-hunted document
paths, the hook ingests those docs into the real store, re-runs the query, and
returns the re-evaluated :class:`~activerag.evidence.EvidenceVerdict`. This module
never learns whether that hook is the real registry-backed one or a test fake --
both satisfy the same alias, so the whole orchestration loop stays fixture-testable
with no live Qdrant/GPU, while the real closure drops in WITHOUT any edit to this
module's internals. That real closure is
:func:`activerag.refresh_hook.make_refresh_and_research` (backed by
:class:`activerag.registry_bridge.RegistryBridge`, which rebuilds the registry via
``agenticrag.bootstrap.build_registry``). The physical-headroom check and the
per-source hunt callables are injected for the same reason -- this module owns the
*control flow*, never the hardware or the registry.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, Sequence, Union

from activerag.evidence import (
    AnswerLike,
    EvidenceVerdict,
    RouteResultLike,
    evaluate as evaluate_evidence,
)
from activerag.priority import SourceCandidate, rank_sources
from activerag.telemetry import HuntEvent, SourceProbeRecord, append_event

if TYPE_CHECKING:  # HuntDecision is only a type here -- injected at runtime, so
    # this module never needs to import headroom_gate (and its numpy/sibling pull).
    from activerag.headroom_gate import HuntDecision

PathLike = Union[str, Path]

# A hunt source: a zero-arg callable returning paths to newly-available content.
# This is EXACTLY RAGpack.ingest_and_retry's ``hunt_fn`` contract and
# StagingDirHuntSource.__call__'s signature -- so a StagingDirHuntSource instance
# already IS a HuntFn, with no adapter.
HuntFn = Callable[[], Iterable[PathLike]]

# The injected re-search/re-ingest hook (see the module docstring). Given
# (query, source_type, freshly-hunted docs) it ingests those docs into the real
# store, re-runs the query, and returns the re-evaluated EvidenceVerdict. Kept a
# plain Callable alias so the real registry_bridge-backed closure and any fake
# test double are interchangeable without this module importing either.
RefreshAndResearch = Callable[[str, str, Sequence[Path]], EvidenceVerdict]

# The injected physical-headroom gate. Given the candidate about to be hunted it
# returns a HuntDecision (headroom_gate.HuntDecision-shaped); only may_hunt=True
# permits the hunt -- DEFER/DENY skip THIS hunt and move on to the next candidate.
GateFn = Callable[[SourceCandidate], "HuntDecision"]


@dataclass
class OrchestrationResult:
    """Outcome of one bounded hunt cycle.

    ``event`` is the exact :class:`~activerag.telemetry.HuntEvent` that was
    appended to the telemetry trail this cycle, or ``None`` when the evidence was
    already sufficient and no hunt cycle ran (nothing is written on a
    short-circuit -- the trail records hunts, and no hunt happened).
    """

    initial_verdict: EvidenceVerdict
    final_verdict: EvidenceVerdict
    hunted: bool                 # at least one real hunt_fn was actually invoked
    resolved: bool               # a hunt improved the verdict to sufficient
    winning_source: str | None   # the source_type whose hunt resolved it, if any
    docs_ingested: int           # total docs handed to refresh_and_research
    attempts: list[SourceProbeRecord]
    event: HuntEvent | None


def run_hunt_cycle(
    *,
    query: str,
    answer: AnswerLike,
    route_result: RouteResultLike,
    entity_hints: Sequence[str],
    known_source_types: Sequence[str],
    hunt_sources: Mapping[str, HuntFn],
    refresh_and_research: RefreshAndResearch,
    gate: GateFn,
    telemetry_path: PathLike,
) -> OrchestrationResult:
    """Run one bounded hunt-and-retry cycle for ``answer`` (routed via
    ``route_result``) and return its :class:`OrchestrationResult`.

    Flow:

    1. Evaluate the existing evidence (``evidence.evaluate``). If it is already
       sufficient, SHORT-CIRCUIT: no ranking, no gate, no hunt, no telemetry --
       ``hunted`` is ``False`` and ``event`` is ``None``.
    2. Otherwise rank the candidate sources (``priority.rank_sources``) and, for
       each in priority order, exactly once:

       * skip with ``no_hunt_source`` if no ``hunt_sources`` entry exists for it;
       * consult ``gate``; on DEFER/DENY record ``gated_*`` and skip this hunt;
       * call its ``hunt_fn``; on an empty result record ``found_nothing`` and
         continue;
       * else hand the found docs to ``refresh_and_research`` and re-evaluate. If
         the new verdict is sufficient, this is the winning hunt -- record it and
         STOP (bounded: first improvement wins). If not, record
         ``still_insufficient_*`` and continue to the next candidate.
    3. Append ONE :class:`~activerag.telemetry.HuntEvent` recording every attempt
       above, then return.

    The cycle is bounded by the length of the ranked candidate list and never
    revisits a candidate.
    """
    started = time.monotonic()
    initial_verdict = evaluate_evidence(answer, route_result)

    # Short-circuit: evidence already sufficient -> no hunt cycle at all.
    if initial_verdict.sufficient:
        return OrchestrationResult(
            initial_verdict=initial_verdict,
            final_verdict=initial_verdict,
            hunted=False,
            resolved=False,
            winning_source=None,
            docs_ingested=0,
            attempts=[],
            event=None,
        )

    candidates = rank_sources(query, list(entity_hints), list(known_source_types))

    attempts: list[SourceProbeRecord] = []
    final_verdict = initial_verdict
    winning_source: str | None = None
    hunted = False
    docs_ingested = 0

    for candidate in candidates:
        source_type = candidate.source_type
        hunt_fn = hunt_sources.get(source_type)

        # (a) No hunt source registered for this type -- cannot hunt it.
        if hunt_fn is None:
            attempts.append(
                SourceProbeRecord(
                    source_type=source_type,
                    hunted=False,
                    docs_found=0,
                    reason="no_hunt_source",
                )
            )
            continue

        # (b) Physical-headroom gate. DEFER/DENY both mean "not now" -- skip THIS
        # hunt (do not spend the hop) and try the next candidate.
        decision = gate(candidate)
        if not decision.may_hunt:
            attempts.append(
                SourceProbeRecord(
                    source_type=source_type,
                    hunted=False,
                    docs_found=0,
                    reason=f"gated_{decision.decision.value}",
                )
            )
            continue

        # (c) Hunt. hunt_fn is a zero-arg StagingDirHuntSource-shaped callable.
        found = [Path(p) for p in hunt_fn()]
        hunted = True
        if not found:
            attempts.append(
                SourceProbeRecord(
                    source_type=source_type,
                    hunted=True,
                    docs_found=0,
                    reason="found_nothing",
                )
            )
            continue

        # (d) Re-ingest + re-search + re-evaluate, behind the injection boundary.
        new_verdict = refresh_and_research(query, source_type, found)
        docs_ingested += len(found)
        final_verdict = new_verdict

        if new_verdict.sufficient:
            attempts.append(
                SourceProbeRecord(
                    source_type=source_type,
                    hunted=True,
                    docs_found=len(found),
                    reason="sufficient_after_hunt",
                )
            )
            winning_source = source_type
            break  # BOUNDED: first improving hunt wins; stop the cycle.

        attempts.append(
            SourceProbeRecord(
                source_type=source_type,
                hunted=True,
                docs_found=len(found),
                reason=f"still_insufficient_{new_verdict.reason}",
            )
        )
        # continue to the next candidate

    resolved = winning_source is not None
    # capped == the bounded cycle ran out of candidates before the verdict
    # improved (every ranked source was tried and none resolved it).
    capped = not resolved

    event = HuntEvent(
        ts=datetime.now(timezone.utc).isoformat(),
        query=query,
        initial_verdict=asdict(initial_verdict),
        sources_tried=attempts,
        winning_source=winning_source,
        docs_ingested=docs_ingested,
        capped=capped,
        final_verdict=asdict(final_verdict),
        wall_clock_s=time.monotonic() - started,
    )
    append_event(event, Path(telemetry_path))

    return OrchestrationResult(
        initial_verdict=initial_verdict,
        final_verdict=final_verdict,
        hunted=hunted,
        resolved=resolved,
        winning_source=winning_source,
        docs_ingested=docs_ingested,
        attempts=attempts,
        event=event,
    )
