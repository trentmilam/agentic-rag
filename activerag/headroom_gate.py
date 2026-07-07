"""Ask the hardware whether there is physical room to hunt.

When :mod:`activerag.evidence` says an answer is thin, hunting for more evidence
is not free: it costs another retrieval/reasoning hop on the GPU. On a
VRAM-bound, thermally fragile card that hop can be the one that wedges it. So
before the orchestrator (:mod:`activerag.orchestrator`) escalates, it consults a *physical*
budget governor -- not a token/cost governor -- that reads VRAM headroom,
thermal margin to the abort line, and the latency budget, and answers
ALLOW / DEFER / DENY.

That governor is not re-implemented here. It is the ``Headroom`` /
``GpuProfile`` / ``Decision`` machinery from the sibling repo
``rag-reliability`` (``projects/rag-reliability/headroom/headroom.py``), reused
wholesale via the sibling-path import in :mod:`activerag._paths`. That directory
is a FLAT module directory with no ``__init__.py`` (headroom.py, loop.py, ...
live directly in it), so ``add_sibling_paths`` puts the ``headroom/`` directory
ITSELF on ``sys.path`` and ``import headroom`` resolves the flat module -- see
``_paths.py`` for why that differs from the package-root convention linkgraph /
agentic-rag use.

**All GPU telemetry here is SIMULATED and clearly labelled as such.** There is
no ``nvidia-smi`` / ``pynvml`` call anywhere in activerag: the trajectory fed to
the governor is a scripted, deterministic ``headroom.Trajectory``. This matches
rag-reliability/headroom's own established, honest convention -- explicitly
labelled simulated hardware data is the accepted portfolio pattern; the governor
itself never learns it is simulated, it only ever sees numbers exactly as it
would from real telemetry.

The activerag-facing question is narrower than headroom's general "may I
escalate one more hop": here it is specifically "may I afford ONE more hop --
the hunt?" So the ``Decision`` is mapped to a plain ``may_hunt`` boolean: only
``ALLOW`` permits the hunt now; ``DEFER`` ("cool down / evict KV first") and
``DENY`` ("answer with what you have") both mean *not now*.

``Decision``, ``GpuProfile``, ``FRAGILE_3090`` and ``ROOMY_5090`` are re-exported
from this module so a caller can drive the gate without repeating the
sibling-path import itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from activerag._paths import add_sibling_paths

add_sibling_paths()

# Reused wholesale from the sibling repo -- no re-implementation. (E402: the
# sibling path must be on sys.path first, hence the import follows the call.)
from headroom import (  # noqa: E402
    FRAGILE_3090,
    ROOMY_5090,
    SEED,
    Decision,
    GpuProfile,
    GpuState,
    Headroom,
    Trajectory,
)

__all__ = [
    "HuntDecision",
    "HuntHeadroomGate",
    "evaluate_simulated",
    "SIM_HEALTHY_5090",
    "SIM_NEAR_WEDGE_3090",
    # re-exported from headroom for caller convenience
    "Decision",
    "GpuProfile",
    "FRAGILE_3090",
    "ROOMY_5090",
]


# --- Clearly-labelled SIMULATED telemetry --------------------------------------
# Each schedule is the scripted post-hop telemetry (vram_used_mb, temp_c,
# hop_ms) for hops 1..N, fed to a deterministic headroom.Trajectory. These are
# NOT real measurements -- there is no nvidia-smi/pynvml anywhere in activerag.
# They exist so activerag has honest, reproducible inputs to demonstrate and
# test the gate against, in the same explicitly-simulated spirit as
# rag-reliability/headroom's own reference trajectories.

# A roomy 5090 mid-run: cool, lots of VRAM headroom, well inside the latency
# budget -- the gate should ALLOW another hop.
SIM_HEALTHY_5090 = [
    (12000.0, 55.0, 800.0),
    (12500.0, 56.0, 820.0),
    (13000.0, 57.0, 840.0),
]

# A fragile 3090 climbing toward its ~22 GiB wedge point and 83C abort line:
# VRAM rising ~2 GB/hop, temperature rising ~5C/hop. By the last hop the
# observed VRAM is already inside the governor's safety margin of the ceiling --
# the gate should refuse to escalate.
SIM_NEAR_WEDGE_3090 = [
    (18000.0, 72.0, 1200.0),
    (20200.0, 77.0, 1350.0),
    (21800.0, 80.0, 1500.0),
]


@dataclass
class HuntDecision:
    """activerag's answer to "is there room to hunt?" -- the ``Headroom``
    verdict plus the derived boolean the orchestrator actually acts on."""

    may_hunt: bool
    decision: Decision
    reason: str
    hops_observed: int


class HuntHeadroomGate:
    """Thin activerag adapter over the real ``headroom.Headroom`` governor.

    Feed each completed retrieval hop's telemetry with :meth:`observe_hop`, then
    call :meth:`may_hunt` to ask whether the next hop -- the hunt -- is
    physically affordable. Every decision comes straight from
    ``Headroom.gate()``; this class adds only the ALLOW->``may_hunt`` mapping and
    surfaces the governor's own audited reason string.
    """

    def __init__(self, profile: GpuProfile = FRAGILE_3090) -> None:
        self.profile = profile
        self._governor = Headroom(profile)
        self._hops_observed = 0

    def observe_hop(self, state: GpuState) -> None:
        """Record the telemetry sampled after one completed hop."""
        self._governor.observe(state)
        self._hops_observed += 1

    def may_hunt(self) -> HuntDecision:
        """Consult the governor for permission to afford one more hop (the
        hunt). With no hops observed yet, the governor cold-starts to ALLOW --
        the first hunt is permitted unconditionally, exactly as headroom does."""
        decision = self._governor.gate()
        reason = self._governor.log[-1].reason
        return HuntDecision(
            may_hunt=decision is Decision.ALLOW,
            decision=decision,
            reason=reason,
            hops_observed=self._hops_observed,
        )


def evaluate_simulated(
    schedule,
    *,
    profile: GpuProfile = FRAGILE_3090,
    hops_completed: int | None = None,
    seed: int = SEED,
) -> HuntDecision:
    """Replay a SIMULATED telemetry ``schedule`` through the gate and return the
    hunt decision.

    Builds a deterministic ``headroom.Trajectory`` from ``schedule`` (a list of
    ``(vram_used_mb, temp_c, hop_ms)`` tuples), observes ``hops_completed`` hops
    into a fresh :class:`HuntHeadroomGate` (default: all hops in the schedule),
    then asks :meth:`HuntHeadroomGate.may_hunt`. No real hardware is touched.
    """
    trajectory = Trajectory(schedule, seed=seed)
    if hops_completed is None:
        hops_completed = len(trajectory)

    gate = HuntHeadroomGate(profile)
    for hop in range(1, hops_completed + 1):
        gate.observe_hop(trajectory.sample(hop))
    return gate.may_hunt()
