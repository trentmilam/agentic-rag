"""community.assign_communities: connected components over
obsoletes/updates/corrects, matching the real lineage grouping in the fixture."""


def test_widget_transport_family_shares_one_community(graph):
    family_a = ["rfc:RFCX9010", "rfc:RFCX9021", "rfc:RFCX9022", "rfc:RFCX9023", "rfc:RFCX9024",
                "rfc:RFCX9025", "rfc:RFCX9026", "rfc:RFCX9040", "rfc:RFCX9099"]
    communities = {graph.nodes[n].community for n in family_a}
    assert len(communities) == 1


def test_session_handshake_family_shares_a_different_community(graph):
    family_b = ["rfc:RFCX9030", "rfc:RFCX9031", "rfc:RFCX9032"]
    communities_b = {graph.nodes[n].community for n in family_b}
    communities_a = {graph.nodes["rfc:RFCX9010"].community}
    assert len(communities_b) == 1
    assert communities_b != communities_a


def test_errata_joins_the_community_of_the_rfc_it_corrects(graph):
    assert graph.nodes["errata:ERRX100"].community == graph.nodes["rfc:RFCX9021"].community
    assert graph.nodes["errata:ERRX102"].community == graph.nodes["rfc:RFCX9010"].community
    assert graph.nodes["errata:ERRX101"].community == graph.nodes["rfc:RFCX9031"].community


def test_every_node_gets_a_community_assignment(graph):
    assert all(n.community is not None for n in graph.nodes.values())


def test_deterministic_under_input_order_shuffle():
    from linkgraph import community, fixtures, resolve

    g1 = resolve.build_graph(fixtures.FIXTURE_ENTITY_REFS)
    community.assign_communities(g1)
    g2 = resolve.build_graph(list(reversed(fixtures.FIXTURE_ENTITY_REFS)))
    community.assign_communities(g2)

    assert {n: g1.nodes[n].community for n in g1.nodes} == {n: g2.nodes[n].community for n in g2.nodes}
