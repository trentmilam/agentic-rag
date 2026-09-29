"""Tests for activerag.priority."""
from __future__ import annotations

from activerag.priority import rank_sources


def test_deterministic_ordering_same_inputs_always_produce_same_output():
    known = ["registry_a", "registry_b", "internet"]
    hints = ["registry_b"]

    first = rank_sources("q", hints, known)
    second = rank_sources("q", hints, known)

    assert first == second
    assert [c.source_type for c in first] == ["registry_b", "registry_a", "internet"]
    assert [c.priority_rank for c in first] == [1, 2, 3]


def test_internet_always_sorts_last_regardless_of_hints():
    known = ["registry_a", "registry_b", "internet"]
    # "internet" is hinted FIRST; it must still land last.
    hints = ["internet", "registry_a"]

    ranked = rank_sources("q", hints, known)

    assert ranked[-1].source_type == "internet"
    assert ranked[-1].priority_rank == len(known)
    # And it never outranks a real source even though it was hinted.
    assert all(c.priority_rank < ranked[-1].priority_rank for c in ranked[:-1])


def test_internet_not_present_when_not_in_known_source_types():
    known = ["registry_a", "registry_b"]
    hints = ["internet"]  # hinted but not a known source type: ignored

    ranked = rank_sources("q", hints, known)

    assert "internet" not in [c.source_type for c in ranked]
    assert len(ranked) == 2


def test_hinted_source_outranks_unhinted_source():
    known = ["alpha", "beta", "gamma"]
    hints = ["gamma"]

    ranked = rank_sources("q", hints, known)
    rank_by_type = {c.source_type: c.priority_rank for c in ranked}

    assert rank_by_type["gamma"] < rank_by_type["alpha"]
    assert rank_by_type["gamma"] < rank_by_type["beta"]


def test_unhinted_sources_keep_their_relative_caller_supplied_order():
    known = ["alpha", "beta", "gamma", "delta"]
    hints = ["gamma"]

    ranked = rank_sources("q", hints, known)

    assert [c.source_type for c in ranked] == ["gamma", "alpha", "beta", "delta"]


def test_hint_order_is_respected_for_multiple_hinted_sources():
    known = ["alpha", "beta", "gamma"]
    hints = ["gamma", "alpha"]

    ranked = rank_sources("q", hints, known)

    assert [c.source_type for c in ranked] == ["gamma", "alpha", "beta"]


def test_duplicate_hints_are_deduplicated():
    known = ["alpha", "beta"]
    hints = ["beta", "beta", "beta"]

    ranked = rank_sources("q", hints, known)

    assert [c.source_type for c in ranked] == ["beta", "alpha"]
