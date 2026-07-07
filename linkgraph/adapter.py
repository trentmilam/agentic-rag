"""The two boundary crossings: ``export_graphrx_graph`` (linkgraph's own
``LinkGraph`` -> the confirmed ``graphrx`` shape) and ``load_from_export``
(a real ``candidates.jsonl`` file -> ``list[EntityRef]``).

Confirmed ``graphrx`` contract (read from ``rag-reliability/graphrx/graphrx/``
directly, not assumed)::

    graph = {"nodes": {id: {"facts": [...], "community": ...}},
             "edges": [(u, v), ...],
             "facts": {id: {"text", "real_entity", "real_community"}}}

``graphrx.graph.adjacency()`` does a strict 2-tuple unpack over ``edges`` and
crashes on anything richer, so every edge here is flattened to its plain
undirected endpoints on export -- linkgraph's own typed/directed/scored edges
are the internal representation; only the flattened form crosses the
boundary. Nodes tolerate arbitrary extra keys (only ``facts``/``community``
are read by ``graphrx``), so ``entity_type`` is included for readability.
"""
from __future__ import annotations

import json

from .contract import EntityRef
from .graph import LinkGraph


def export_graphrx_graph(graph: LinkGraph, min_edge_score: float = 0.0) -> dict:
    """``min_edge_score`` filters ONLY ``co_mentions`` edges before flattening
    (same convention as ``LinkGraph.get_related``'s ``min_score`` -- the other
    three edge types are asserted facts, not a scored signal to threshold).

    Precondition: call ``community.assign_communities(graph)`` first for a
    meaningful ``community`` label. A node with no assignment yet falls back
    to its own id as a singleton label, so this never crashes -- but that
    fallback is not a substitute for real assignment.
    """
    nodes: dict[str, dict] = {}
    facts: dict[str, dict] = {}
    fact_seq = 0

    for node_id, node in graph.nodes.items():
        community = node.community if node.community is not None else node_id
        fact_ids = []
        for text in node.raw_texts:
            fact_id = f"fact{fact_seq}"
            fact_seq += 1
            facts[fact_id] = {"text": text, "real_entity": node_id, "real_community": community}
            fact_ids.append(fact_id)
        nodes[node_id] = {"facts": fact_ids, "community": community, "entity_type": node.entity_type}

    seen_pairs: set[tuple[str, str]] = set()
    edges: list[tuple[str, str]] = []
    for e in graph.edges:
        if e.edge_type == "co_mentions" and e.score < min_edge_score:
            continue
        pair = tuple(sorted((e.src, e.dst)))
        if pair in seen_pairs or pair[0] == pair[1]:
            continue
        seen_pairs.add(pair)
        edges.append(pair)

    return {"nodes": nodes, "edges": sorted(edges), "facts": facts}


def load_from_export(candidates_jsonl_path: str) -> list[EntityRef]:
    """The documented, swappable loader: reads a real ``candidates.jsonl``
    file (one JSON object per line, per the contract in ``contract.py``) into
    ``EntityRef``s. Makes no fixture-specific assumptions -- every field is
    read generically, so this is expected to work unmodified once
    agentic-rag's real ingest emits the real file; point it there instead of
    a fixture path and nothing else changes.
    """
    refs: list[EntityRef] = []
    with open(candidates_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            refs.append(
                EntityRef(
                    entity_type=obj["entity_type"],
                    entity_id=str(obj["entity_id"]),
                    raw_text=obj["raw_text"],
                    doc_id=obj["doc_id"],
                    resolved=bool(obj["resolved"]),
                    extra=dict(obj.get("extra") or {}),
                )
            )
    return refs
