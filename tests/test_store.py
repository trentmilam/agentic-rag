"""SQLite persistence round-trip: save_graph -> load_graph must reconstruct
an equal graph (nodes, raw_texts, community, seen_as_primary, edges)."""
from linkgraph import store


def test_round_trip_preserves_nodes_and_edges(graph, tmp_path):
    db_path = str(tmp_path / "linkdb.sqlite")
    store.save_graph(graph, db_path)
    loaded = store.load_graph(db_path)

    assert set(loaded.nodes) == set(graph.nodes)
    for node_id, node in graph.nodes.items():
        loaded_node = loaded.nodes[node_id]
        assert loaded_node.entity_type == node.entity_type
        assert loaded_node.community == node.community
        assert loaded_node.seen_as_primary == node.seen_as_primary
        assert loaded_node.raw_texts == node.raw_texts

    assert sorted((e.src, e.dst, e.edge_type, e.score) for e in loaded.edges) == \
        sorted((e.src, e.dst, e.edge_type, e.score) for e in graph.edges)


def test_round_trip_preserves_dangling_node_with_empty_raw_texts(graph, tmp_path):
    db_path = str(tmp_path / "linkdb.sqlite")
    store.save_graph(graph, db_path)
    loaded = store.load_graph(db_path)

    dangling = loaded.nodes["rfc:RFCX9099"]
    assert dangling.seen_as_primary is False
    assert dangling.raw_texts == []


def test_communities_table_matches_entities_community_column(graph, tmp_path):
    import sqlite3

    db_path = str(tmp_path / "linkdb.sqlite")
    store.save_graph(graph, db_path)

    conn = sqlite3.connect(db_path)
    try:
        from_communities = {
            node_id for (node_id,) in conn.execute(
                "SELECT node_id FROM communities WHERE community_id = ?",
                (graph.nodes["rfc:RFCX9010"].community,),
            )
        }
        from_entities = {
            n.node_id for n in graph.nodes.values()
            if n.community == graph.nodes["rfc:RFCX9010"].community
        }
    finally:
        conn.close()
    assert from_communities == from_entities


def test_save_graph_overwrites_a_prior_db(graph, tmp_path):
    db_path = str(tmp_path / "linkdb.sqlite")
    store.save_graph(graph, db_path)
    store.save_graph(graph, db_path)  # must not fail or duplicate rows
    loaded = store.load_graph(db_path)
    assert len(loaded.edges) == len(graph.edges)
