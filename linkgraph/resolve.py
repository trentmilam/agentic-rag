"""Graph construction: turn a stream of ``EntityRef`` mentions into a
``LinkGraph`` -- nodes, directed ``obsoletes``/``updates``/``corrects`` edges
read straight from each mention's ``extra``, and a ``co_mentions`` pass
grouped by ``doc_id``.

``entity_type="registry"`` mentions are skipped outright: per the source
contract, registry entities are never cross-referenced by anything else in
the corpus, so there is no graph structure to build from them here.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .contract import EntityRef
from .graph import LinkGraph
from .scoring import co_mention_scores

_GRAPH_ENTITY_TYPES = {"rfc", "errata"}


def build_graph(entity_refs: Iterable[EntityRef]) -> LinkGraph:
    g = LinkGraph()
    doc_groups: dict[str, set[str]] = defaultdict(set)

    for ref in entity_refs:
        if ref.entity_type not in _GRAPH_ENTITY_TYPES:
            continue

        node_id = f"{ref.entity_type}:{ref.entity_id}"
        g.ensure_node(node_id, ref.entity_type)
        g.mark_primary(node_id, ref.raw_text)
        doc_groups[ref.doc_id].add(node_id)

        if ref.entity_type == "rfc":
            for target in ref.extra.get("obsoletes", []):
                other = f"rfc:{target}"
                g.ensure_node(other, "rfc")
                g.add_edge(node_id, other, "obsoletes")
            for source in ref.extra.get("obsoleted_by", []):
                other = f"rfc:{source}"
                g.ensure_node(other, "rfc")
                g.add_edge(other, node_id, "obsoletes")
            for target in ref.extra.get("updates", []):
                other = f"rfc:{target}"
                g.ensure_node(other, "rfc")
                g.add_edge(node_id, other, "updates")
            for source in ref.extra.get("updated_by", []):
                other = f"rfc:{source}"
                g.ensure_node(other, "rfc")
                g.add_edge(other, node_id, "updates")

        elif ref.entity_type == "errata":
            corrects = ref.extra.get("rfc")
            if corrects is not None:
                other = f"rfc:{corrects}"
                g.ensure_node(other, "rfc")
                g.add_edge(node_id, other, "corrects")

    scores = co_mention_scores(doc_groups)
    for (a, b), score in scores.items():
        g.add_edge(a, b, "co_mentions", score=float(score))

    return g
