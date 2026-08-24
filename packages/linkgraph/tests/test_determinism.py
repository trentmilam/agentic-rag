"""Determinism under input-order shuffling: the full resolve -> community ->
export pipeline must not depend on the order candidates.jsonl lines arrive in."""
import random

from linkgraph import adapter, community, fixtures, resolve


def _canonical_export(entity_refs):
    g = resolve.build_graph(entity_refs)
    community.assign_communities(g)
    gx = adapter.export_graphrx_graph(g)
    # facts are keyed by an insertion-order-dependent "factN" id -- compare by
    # VALUE (the set of (text, real_entity, real_community) triples per node),
    # not by the arbitrary id, so this only asserts genuine structural equality.
    nodes_canon = {
        node_id: (
            frozenset(gx["facts"][fid]["text"] for fid in n["facts"]),
            n["community"],
        )
        for node_id, n in gx["nodes"].items()
    }
    return nodes_canon, sorted(gx["edges"])


def test_shuffle_reversed_order_is_identical():
    base = _canonical_export(fixtures.FIXTURE_ENTITY_REFS)
    reversed_refs = list(reversed(fixtures.FIXTURE_ENTITY_REFS))
    assert _canonical_export(reversed_refs) == base


def test_several_random_shuffles_all_match():
    base = _canonical_export(fixtures.FIXTURE_ENTITY_REFS)
    rng = random.Random(20260706)
    for _ in range(5):
        shuffled = list(fixtures.FIXTURE_ENTITY_REFS)
        rng.shuffle(shuffled)
        assert _canonical_export(shuffled) == base
