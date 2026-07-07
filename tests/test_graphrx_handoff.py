"""The graphrx hand-off integration proof: export_graphrx_graph() round-trips
through graphrx.graph.adjacency(), a clean fixture produces zero high-risk
defects from the UNMODIFIED graphrx.lint.report(), and a fixture with a
deliberately planted bad merge is correctly flagged by that same unmodified
mechanism."""
import copy

from linkgraph import adapter

from graphrx.graph import adjacency
from graphrx.lint import high_risk, report

HIGH_RISK = 0.25


def plant_bad_merge(gx_graph: dict, node_a: str, node_b: str, merged_id: str) -> dict:
    """Merge two real, distinct linkgraph nodes into one -- the SAME technique
    graphrx/fixtures.py's build_flawed_graph uses to plant its own ER-collision
    defect: concatenate both nodes' facts, redirect every edge touching either
    original endpoint to the merged id, drop the two originals, keep one
    node's community label. Operates on a deep copy; the input is untouched.
    """
    g = copy.deepcopy(gx_graph)
    facts_a = g["nodes"][node_a]["facts"]
    facts_b = g["nodes"][node_b]["facts"]
    community_label = g["nodes"][node_a]["community"]
    g["nodes"][merged_id] = {"facts": facts_a + facts_b, "community": community_label}
    del g["nodes"][node_a]
    del g["nodes"][node_b]
    new_edges = []
    for u, v in g["edges"]:
        u2 = merged_id if u in (node_a, node_b) else u
        v2 = merged_id if v in (node_a, node_b) else v
        if u2 == v2:
            continue
        new_edges.append(tuple(sorted((u2, v2))))
    g["edges"] = sorted(set(new_edges))
    return g


def test_export_shape_matches_the_confirmed_graphrx_contract(graph):
    gx = adapter.export_graphrx_graph(graph)
    assert set(gx.keys()) == {"nodes", "edges", "facts"}
    for node in gx["nodes"].values():
        assert "facts" in node and "community" in node
    for fact in gx["facts"].values():
        assert {"text", "real_entity", "real_community"} <= set(fact.keys())


def test_edges_are_flattened_to_plain_2tuples(graph):
    gx = adapter.export_graphrx_graph(graph)
    for edge in gx["edges"]:
        assert isinstance(edge, tuple)
        assert len(edge) == 2


def test_export_round_trips_through_graphrx_adjacency(graph):
    gx = adapter.export_graphrx_graph(graph)
    adj = adjacency(gx)  # must not crash on a strict 2-tuple unpack
    assert adj["rfc:RFCX9021"] >= {"rfc:RFCX9010"}
    # adjacency is symmetric even though our own edge was directed internally
    assert "rfc:RFCX9021" in adj["rfc:RFCX9010"]


def test_clean_fixture_has_zero_high_risk_defects(graph):
    gx = adapter.export_graphrx_graph(graph)
    defects = report(gx)
    assert high_risk(defects, HIGH_RISK) == []


def test_planted_bad_merge_is_flagged_by_unmodified_lint_report(graph):
    gx = adapter.export_graphrx_graph(graph)
    # rfc:RFCX9021 (Widget Transport / multiplex vocabulary) and rfc:RFCX9031
    # (Session Handshake / cipher vocabulary) are real, distinct, cross-family
    # nodes -- exactly the kind of accidental entity-resolution merge that
    # should never happen but must be CAUGHT when it does.
    bad = plant_bad_merge(gx, "rfc:RFCX9021", "rfc:RFCX9031", "rfc:RFCX9021+RFCX9031")

    defects = report(bad)
    by_kind = {d["kind"]: d for d in defects if d["target"] == "rfc:RFCX9021+RFCX9031"}

    assert "er_collision" in by_kind
    assert by_kind["er_collision"]["score"] >= HIGH_RISK
    assert by_kind["er_collision"] in high_risk(defects, HIGH_RISK)


def test_planted_bad_merge_split_proposal_is_entity_pure(graph):
    gx = adapter.export_graphrx_graph(graph)
    bad = plant_bad_merge(gx, "rfc:RFCX9021", "rfc:RFCX9031", "rfc:RFCX9021+RFCX9031")
    defects = report(bad)
    collision = next(d for d in defects if d["kind"] == "er_collision" and d["target"] == "rfc:RFCX9021+RFCX9031")

    clusters = collision["proposal"]["clusters"]
    assert len(clusters) == 2
    for part in clusters:
        real_entities = {bad["facts"][fid]["real_entity"] for fid in part}
        # a PURE split recovers exactly the true merged-in entity per side
        assert len(real_entities) == 1


def test_bad_merge_mutation_does_not_affect_the_original_export(graph):
    gx = adapter.export_graphrx_graph(graph)
    before = copy.deepcopy(gx)
    plant_bad_merge(gx, "rfc:RFCX9021", "rfc:RFCX9031", "rfc:RFCX9021+RFCX9031")
    assert gx == before
