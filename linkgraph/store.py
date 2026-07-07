"""SQLite persistence for the ``LinkGraph`` -- ``linkdb.sqlite``.

Schema, kept simple and matching the in-memory model 1:1:

    entities(node_id PK, entity_type, community, seen_as_primary, raw_texts_json)
    edges(id PK autoincrement, src, dst, edge_type, score)
    communities(community_id, node_id)  -- PK(community_id, node_id)

``communities`` is a membership index that is otherwise recoverable from
``entities.community`` -- it exists so "every member of community N" is a
plain indexed lookup rather than a full-table scan, and ``save_graph`` always
DERIVES it fresh from ``entities.community``, so the two can never drift out
of sync with each other.
"""
from __future__ import annotations

import json
import sqlite3

from .graph import Edge, LinkGraph, Node

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    node_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    community INTEGER,
    seen_as_primary INTEGER NOT NULL,
    raw_texts_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    score REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS communities (
    community_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    PRIMARY KEY (community_id, node_id)
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def save_graph(graph: LinkGraph, db_path: str) -> None:
    """Overwrite ``db_path`` with the current graph state (drop + recreate
    all three tables, then write everything fresh -- simplest correct
    behavior for a showcase-scale graph; no incremental-update path).
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            "DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS communities;"
        )
        init_db(conn)

        conn.executemany(
            "INSERT INTO entities (node_id, entity_type, community, seen_as_primary, raw_texts_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (n.node_id, n.entity_type, n.community, int(n.seen_as_primary), json.dumps(n.raw_texts))
                for n in graph.nodes.values()
            ],
        )
        conn.executemany(
            "INSERT INTO edges (src, dst, edge_type, score) VALUES (?, ?, ?, ?)",
            [(e.src, e.dst, e.edge_type, e.score) for e in graph.edges],
        )
        conn.executemany(
            "INSERT INTO communities (community_id, node_id) VALUES (?, ?)",
            [(n.community, n.node_id) for n in graph.nodes.values() if n.community is not None],
        )
        conn.commit()
    finally:
        conn.close()


def load_graph(db_path: str) -> LinkGraph:
    conn = sqlite3.connect(db_path)
    try:
        graph = LinkGraph()
        for node_id, entity_type, community, seen_as_primary, raw_texts_json in conn.execute(
            "SELECT node_id, entity_type, community, seen_as_primary, raw_texts_json FROM entities"
        ):
            graph.nodes[node_id] = Node(
                node_id=node_id,
                entity_type=entity_type,
                raw_texts=json.loads(raw_texts_json),
                community=community,
                seen_as_primary=bool(seen_as_primary),
            )
        for src, dst, edge_type, score in conn.execute("SELECT src, dst, edge_type, score FROM edges"):
            graph.edges.append(Edge(src, dst, edge_type, score))
            graph._edge_keys.add((src, dst, edge_type))
        return graph
    finally:
        conn.close()
