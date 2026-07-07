"""resolve.build_graph: edge direction correctness, redundant-declaration
dedup, and registry-entity exclusion."""
from linkgraph.contract import EntityRef
from linkgraph.resolve import build_graph


def _edge_set(g):
    return {(e.src, e.dst, e.edge_type) for e in g.edges}


def test_obsoletes_direction_is_successor_to_predecessor(graph):
    # "RFCX9021 obsoletes RFCX9010" must be stored as (RFCX9021 -> RFCX9010), never
    # the reverse -- get_obsoletion_chain's status logic depends on this.
    assert ("rfc:RFCX9021", "rfc:RFCX9010", "obsoletes") in _edge_set(graph)
    assert ("rfc:RFCX9010", "rfc:RFCX9021", "obsoletes") not in _edge_set(graph)


def test_obsoleted_by_is_normalized_to_the_same_direction(graph):
    # RFCX9010's OWN record declares obsoleted_by=[RFCX9021..RFCX9026]; that must
    # produce the identical (successor -> predecessor) edges as each
    # successor's own "obsoletes" declaration, not a reversed duplicate set.
    for successor in ("RFCX9021", "RFCX9022", "RFCX9023", "RFCX9024", "RFCX9025", "RFCX9026"):
        assert (f"rfc:{successor}", "rfc:RFCX9010", "obsoletes") in _edge_set(graph)


def test_redundant_bidirectional_declaration_dedups_to_one_edge():
    # RFCX-prefixed even in this minimal local fixture: a bare small integer
    # like "1"/"2" is just as much a real, currently-assigned RFC number as a
    # large one (RFC assignment has no reliably permanent unused range).
    refs = [
        EntityRef("rfc", "RFCXL1", "t", "d1", True, {"obsoletes": ["RFCXL2"]}),
        EntityRef("rfc", "RFCXL2", "t", "d2", True, {"obsoleted_by": ["RFCXL1"]}),
    ]
    g = build_graph(refs)
    obsoletes_edges = [e for e in g.edges if e.edge_type == "obsoletes"]
    assert len(obsoletes_edges) == 1
    assert (obsoletes_edges[0].src, obsoletes_edges[0].dst) == ("rfc:RFCXL1", "rfc:RFCXL2")


def test_updates_direction_and_dedup():
    refs = [
        EntityRef("rfc", "RFCXL40", "t", "d1", True, {"updates": ["RFCXL10"]}),
        EntityRef("rfc", "RFCXL10", "t", "d2", True, {"updated_by": ["RFCXL40"]}),
    ]
    g = build_graph(refs)
    updates_edges = [e for e in g.edges if e.edge_type == "updates"]
    assert len(updates_edges) == 1
    assert (updates_edges[0].src, updates_edges[0].dst) == ("rfc:RFCXL40", "rfc:RFCXL10")


def test_corrects_edge_direction_and_dedup_across_repeated_mentions(graph):
    corrects_edges = [
        (e.src, e.dst) for e in graph.edges
        if e.edge_type == "corrects" and e.dst == "rfc:RFCX9031"
    ]
    # ERRX101 is mentioned TWICE in the fixture (its own record + a body-doc
    # co-mention), both carrying the same rfc=RFCX9031 -- must dedup to 1.
    assert corrects_edges == [("errata:ERRX101", "rfc:RFCX9031")]


def test_dangling_target_gets_a_node_but_is_not_seen_as_primary(graph):
    node = graph.nodes["rfc:RFCX9099"]
    assert node.seen_as_primary is False
    assert node.raw_texts == []


def test_registry_entities_are_excluded_from_the_graph():
    refs = [
        EntityRef("rfc", "RFCXL1", "t", "d1", True, {}),
        EntityRef("registry", "iana-ports", "t", "d1", True, {}),
    ]
    g = build_graph(refs)
    assert "registry:iana-ports" not in g.nodes
    assert len(g.nodes) == 1
    # a registry mention must also not pollute co-mention grouping
    assert not any(e.edge_type == "co_mentions" for e in g.edges)


def test_co_mention_edges_present_for_a_real_shared_doc(graph):
    pairs = {tuple(sorted((e.src, e.dst))) for e in graph.edges if e.edge_type == "co_mentions"}
    assert ("errata:ERRX100", "rfc:RFCX9021") in pairs
    assert ("rfc:RFCX9021", "rfc:RFCX9022") in pairs
