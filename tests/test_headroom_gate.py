"""Tests for activerag.headroom_gate.

Hermetic: all telemetry is the module's clearly-labelled SIMULATED trajectories
driven through a deterministic (seeded) ``headroom.Trajectory``. No nvidia-smi,
no pynvml, no GPU, no network -- matching the no-live-dependency style of the
other activerag tests. The one real cross-repo dependency exercised here is the
sibling-path import of the ``headroom`` flat module (via activerag._paths).
"""
from __future__ import annotations

from activerag.headroom_gate import (
    FRAGILE_3090,
    ROOMY_5090,
    SIM_HEALTHY_5090,
    SIM_NEAR_WEDGE_3090,
    Decision,
    HuntHeadroomGate,
    evaluate_simulated,
)


def test_sibling_import_reuses_the_real_headroom_module():
    # The gate module bootstrapped the sibling path at import; importing headroom
    # here must resolve the SAME flat module, and its classes must be the very
    # objects headroom_gate re-exported (no shadow re-implementation).
    import headroom

    assert Decision is headroom.Decision
    assert FRAGILE_3090 is headroom.FRAGILE_3090
    assert ROOMY_5090 is headroom.ROOMY_5090
    assert Decision.ALLOW.value == "allow"


def test_cold_gate_with_no_observations_allows_the_first_hunt():
    # No telemetry observed yet -> headroom cold-starts to ALLOW, so the first
    # hunt is permitted unconditionally.
    gate = HuntHeadroomGate(FRAGILE_3090)

    result = gate.may_hunt()

    assert result.may_hunt is True
    assert result.decision is Decision.ALLOW
    assert result.hops_observed == 0


def test_healthy_roomy_trajectory_allows_hunt():
    result = evaluate_simulated(SIM_HEALTHY_5090, profile=ROOMY_5090)

    assert result.may_hunt is True
    assert result.decision is Decision.ALLOW
    assert result.hops_observed == len(SIM_HEALTHY_5090)


def test_near_wedge_3090_trajectory_denies_hunt():
    result = evaluate_simulated(SIM_NEAR_WEDGE_3090, profile=FRAGILE_3090)

    assert result.may_hunt is False
    assert result.decision is Decision.DENY
    # The governor's audited reason explains WHY -- VRAM against the ceiling.
    assert "vram" in result.reason.lower()


def test_defer_band_also_blocks_the_hunt_not_only_deny():
    # Stop one hop earlier on the same rising 3090 trajectory: the next hop is
    # predicted into the defer band (cool down / evict first), not yet over the
    # hard line. DEFER must still mean "not now" for a hunt.
    result = evaluate_simulated(
        SIM_NEAR_WEDGE_3090, profile=FRAGILE_3090, hops_completed=2
    )

    assert result.decision is Decision.DEFER
    assert result.may_hunt is False
    assert result.hops_observed == 2


def test_only_allow_maps_to_may_hunt_true():
    # Collect the decision->may_hunt mapping across all three outcomes actually
    # produced by these fixtures and assert only ALLOW yields True.
    allow = evaluate_simulated(SIM_HEALTHY_5090, profile=ROOMY_5090)
    defer = evaluate_simulated(SIM_NEAR_WEDGE_3090, profile=FRAGILE_3090, hops_completed=2)
    deny = evaluate_simulated(SIM_NEAR_WEDGE_3090, profile=FRAGILE_3090)

    mapping = {r.decision: r.may_hunt for r in (allow, defer, deny)}
    assert mapping == {Decision.ALLOW: True, Decision.DEFER: False, Decision.DENY: False}


def test_evaluate_simulated_is_deterministic_across_runs():
    # Same seeded simulated trajectory -> identical verdict every time.
    first = evaluate_simulated(SIM_NEAR_WEDGE_3090, profile=FRAGILE_3090)
    second = evaluate_simulated(SIM_NEAR_WEDGE_3090, profile=FRAGILE_3090)

    assert (first.may_hunt, first.decision, first.reason) == (
        second.may_hunt,
        second.decision,
        second.reason,
    )


def test_reason_is_populated_from_the_governor_log():
    result = evaluate_simulated(SIM_HEALTHY_5090, profile=ROOMY_5090)

    # ALLOW carries headroom's own "headroom ok" reason string.
    assert result.reason
    assert isinstance(result.reason, str)
