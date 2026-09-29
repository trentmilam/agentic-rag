"""Ask the hardware whether there is physical room to hunt.

When :mod:`activerag.evidence` says an answer is thin, hunting for more evidence
is not free: it costs another retrieval/reasoning hop on the GPU. On a
VRAM-bound, thermally fragile card that hop can be the one that wedges it. So
before the orchestrator (:mod:`activerag.orchestrator`) escalates, it consults
a *physical* budget governor, not a token/cost governor, that reads VRAM
headroom, thermal margin to the abort line, and the latency budget, and
answers ALLOW / DEFER / DENY.

That governor is not re-implemented here. It is the ``Headroom`` /
``GpuProfile`` / ``Decision`` machinery from the sibling repo
``rag-reliability`` (``headroom/headroom.py``, cloned next to the agentic-rag
repo itself), reused wholesale via the sibling-path import in
:mod:`activerag._paths`. That directory is a flat module directory with no
``__init__.py`` (headroom.py, loop.py, ... live directly in it), so
``add_sibling_paths`` puts the ``headroom/`` directory itself on ``sys.path``
and ``import headroom`` resolves the flat module; see ``_paths.py`` for why
that differs from the package-root convention linkgraph / agentic-rag use.

**All GPU telemetry here is simulated and clearly labelled as such.** There is
no ``nvidia-smi`` / ``pynvml`` call anywhere in activerag: the trajectory fed to
the governor is a scripted, deterministic ``headroom.Trajectory``. This matches
rag-reliability/headroom's own established convention of explicitly labelling
simulated hardware data; the governor itself never learns it is simulated, it
only ever sees numbers exactly as it would from real telemetry.

The activerag-facing question is narrower than headroom's general "may I
escalate one more hop": here it is specifically "may I afford one more hop,
the hunt?" So the ``Decision`` is mapped to a plain ``may_hunt`` boolean: only
``ALLOW`` permits the hunt now; ``DEFER`` ("cool down / evict KV first") and
``DENY`` ("answer with what you have") both mean *not now*.

``Decision``, ``GpuProfile``, ``CARD_A`` and ``CARD_B`` are re-exported
from this module so a caller can drive the gate without repeating the
sibling-path import itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from activerag._paths import add_sibling_paths

add_sibling_paths()

# Reused wholesale from the sibling repo; no re-implementation. (E402: the
# sibling path must be on sys.path first, hence the import follows the call.)
from headroom import (  # noqa: E402
    CARD_A,
    CARD_B,
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
    "SIM_HEALTHY_ROOMY",
    "SIM_NEAR_WEDGE_TIGHT",
    # re-exported from headroom for caller convenience
    "Decision",
    "GpuProfile",
    "CARD_A",
    "CARD_B",
]


# --- Clearly-labelled simulated telemetry --------------------------------------
# Each schedule is the scripted post-hop telemetry (vram_used_mb, temp_c,
# hop_ms) for hops 1..N, fed to a deterministic headroom.Trajectory. These are
# not real measurements; there is no nvidia-smi/pynvml anywhere in activerag.
# They exist so activerag has honest, reproducible inputs to demonstrate and
# test the gate against, in the same explicitly-simulated spirit as
# rag-reliability/headroom's own reference trajectories. The numbers are sized to
# headroom's two illustrative reference profiles: CARD_B (the roomier 24 GB
# example) and CARD_A (the tighter 16 GB / lower-margin example).

# A roomy card (CARD_B) mid-run: cool, plenty of VRAM headroom, well inside the
# latency budget. The gate should ALLOW another hop.
SIM_HEALTHY_ROOMY = [
    (12000.0, 55.0, 800.0),
    (12500.0, 56.0, 820.0),
    (13000.0, 57.0, 840.0),
]

# A tight-margin card (CARD_A) climbing toward its 15 GB ceiling and 90C abort
# line: VRAM rising ~1.3 GB/hop, temperature ~4C/hop. Stop at hop 2 and the next
# hop is predicted into the governor's DEFER band (evict/cool first); run the
# full schedule and by hop 3 the observed VRAM is already inside the safety
# margin of the ceiling, so the gate DENIES another hop.
SIM_NEAR_WEDGE_TIGHT = [
    (11500.0, 78.0, 1200.0),
    (12800.0, 82.0, 1300.0),
    (14100.0, 86.0, 1400.0),
]


@dataclass
class HuntDecision:
    """activerag's answer to "is there room to hunt?": the ``Headroom``
    verdict plus the derived boolean the orchestrator actually acts on."""

    may_hunt: bool
    decision: Decision
    reason: str
    hops_observed: int


class HuntHeadroomGate:
    """Thin activerag adapter over the real ``headroom.Headroom`` governor.

    Feed each completed retrieval hop's telemetry with :meth:`observe_hop`, then
    call :meth:`may_hunt` to ask whether the next hop, the hunt, is
    physically affordable. Every decision comes straight from
    ``Headroom.gate()``; this class adds only the ALLOW->``may_hunt`` mapping and
    surfaces the governor's own audited reason string.
    """

    def __init__(self, profile: GpuProfile = CARD_A) -> None:
        self.profile = profile
        self._governor = Headroom(profile)
        self._hops_observed = 0

    def observe_hop(self, state: GpuState) -> None:
        """Record the telemetry sampled after one completed hop."""
        self._governor.observe(state)
        self._hops_observed += 1

    def may_hunt(self) -> HuntDecision:
        """Consult the governor for permission to afford one more hop (the
        hunt). With no hops observed yet, the governor cold-starts to ALLOW:
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
    profile: GpuProfile = CARD_A,
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
