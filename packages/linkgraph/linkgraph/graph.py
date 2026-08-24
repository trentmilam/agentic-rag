"""The in-memory LinkGraph: nodes keyed by a namespaced id (``rfc:<number>`` /
``errata:<id>``) plus a typed, directed-by-default edge list, with a small
traversal API on top (``get_related`` / ``get_obsoletion_chain`` /
``get_corrections``).

An RFC number is already a stable, unambiguous identity (obsoletion mints an
entirely NEW number rather than revising an existing one), so unlike a
letter-revisioned part there is no separate "family/revision" node to split
out -- one node per real RFC, one node per real erratum. This is simpler than
a revision-chain model on purpose.

Edge types, all real (nothing fabricated):

* ``obsoletes``  -- directed, ``(A, B)`` means "A obsoletes B". Many-to-many:
  a single RFC can obsolete several others, and be obsoleted by several
  others (the real RFC 2616 -> {7230..7235} shape).
* ``updates``    -- directed, ``(A, B)`` means "A updates B" (does not retire
  B -- a materially weaker relationship than obsoletion).
* ``corrects``   -- directed, ``(errata, rfc)``.
* ``co_mentions``-- undirected, scored (see ``scoring.py``); a much weaker,
  noisier signal than the three structural edge types above.

``min_score`` filtering (``get_related``) and the ``graphrx`` export's
``min_edge_score`` (``adapter.py``) apply ONLY to ``co_mentions`` edges. The
other three are asserted facts pulled directly from the source data, not a
probabilistic signal -- there is nothing for a score threshold to mean there.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional

EDGE_TYPES = ("obsoletes", "updates", "corrects", "co_mentions")


@dataclass
class Node:
    node_id: str
    entity_type: str  # "rfc" | "errata"
    raw_texts: list[str] = field(default_factory=list)
    community: Optional[int] = None
    # True iff this node was built from at least one EntityRef whose own
    # entity_type/entity_id named it directly. False means it is known ONLY
    # because something else's obsoletes/obsoleted_by/updates/updated_by/
    # rfc (errata's corrects-target key) pointed at it -- a dangling reference (see get_obsoletion_chain).
    seen_as_primary: bool = False


@dataclass
class Edge:
    src: str
    dst: str
    edge_type: str  # one of EDGE_TYPES
    score: float = 1.0  # meaningful only for "co_mentions"; structural edges are asserted facts


class LinkGraph:
    """Mutable node/edge store. Built by ``resolve.build_graph``; queried here."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()  # dedup guard

    # -- construction -------------------------------------------------
    def ensure_node(self, node_id: str, entity_type: str) -> Node:
        node = self.nodes.get(node_id)
        if node is None:
            node = Node(node_id=node_id, entity_type=entity_type)
            self.nodes[node_id] = node
        return node

    def mark_primary(self, node_id: str, raw_text: str) -> None:
        node = self.nodes[node_id]
        node.seen_as_primary = True
        node.raw_texts.append(raw_text)

    def add_edge(self, src: str, dst: str, edge_type: str, score: float = 1.0) -> None:
        """Add a directed edge, deduping exact (src, dst, edge_type) repeats.

        Real ``candidates.jsonl`` data is expected to be redundant on purpose
        (the real RFC index annotates BOTH directions -- an RFC's own record
        lists what it obsoletes, and the RFC it obsoletes independently lists
        what obsoleted it) -- this dedup is what makes that redundancy safe to
        just re-process rather than requiring the caller to pre-filter it.
        """
        key = (src, dst, edge_type)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(Edge(src, dst, edge_type, score))

    # -- traversal ------------------------------------------------------
    def _adjacency(self, edge_types: Optional[set[str]], min_score: float) -> dict[str, set[str]]:
        """Undirected adjacency filtered by edge type + (co_mentions-only) score.

        "Related" is a symmetric notion even though obsoletes/updates/corrects
        are stored directed: if A obsoletes B, B is unquestionably related to
        A too. Mirrors graphrx.graph.adjacency()'s own shape/style.
        """
        adj: dict[str, set[str]] = {n: set() for n in self.nodes}
        for e in self.edges:
            if edge_types is not None and e.edge_type not in edge_types:
                continue
            if e.edge_type == "co_mentions" and e.score < min_score:
                continue
            adj.setdefault(e.src, set()).add(e.dst)
            adj.setdefault(e.dst, set()).add(e.src)
        return adj

    def get_related(
        self,
        entity_id: str,
        max_hops: int = 1,
        min_score: float = 0.0,
        edge_types: Optional[Iterable[str]] = None,
    ) -> list[tuple[str, int]]:
        """BFS out from ``entity_id`` (a full node id, e.g. ``"rfc:RFCX9021"``) up
        to ``max_hops``. Returns ``(node_id, hop_distance)`` pairs, excluding
        the seed itself, sorted by ``(hop_distance, node_id)`` for
        determinism.
        """
        types = set(edge_types) if edge_types is not None else None
        adj = self._adjacency(types, min_score)
        if entity_id not in self.nodes:
            return []
        dist = {entity_id: 0}
        frontier = deque([entity_id])
        while frontier:
            u = frontier.popleft()
            if dist[u] >= max_hops:
                continue
            for w in sorted(adj.get(u, ())):
                if w not in dist:
                    dist[w] = dist[u] + 1
                    frontier.append(w)
        related = [(n, d) for n, d in dist.items() if n != entity_id]
        return sorted(related, key=lambda nd: (nd[1], nd[0]))

    def _obsoletes_component(self, node_id: str) -> set[str]:
        """Every node reachable from ``node_id`` via ``obsoletes`` edges only,
        undirected -- the full connected "obsoletion component", branches and
        all. ``updates``/``corrects``/``co_mentions`` are deliberately excluded:
        an update does not retire its target, so it is not part of a
        supersession *history*.
        """
        adj: dict[str, set[str]] = {}
        for e in self.edges:
            if e.edge_type != "obsoletes":
                continue
            adj.setdefault(e.src, set()).add(e.dst)
            adj.setdefault(e.dst, set()).add(e.src)
        if node_id not in adj and node_id not in self.nodes:
            return set()
        seen = {node_id}
        stack = [node_id]
        while stack:
            u = stack.pop()
            for w in sorted(adj.get(u, ()) - seen):
                seen.add(w)
                stack.append(w)
        return seen

    def get_obsoletion_chain(self, rfc_id: str) -> dict:
        """Walk the REAL obsoletes/obsoleted-by edges reachable from
        ``rfc_id`` (a bare RFC id, e.g. ``"RFCX9010"``, not prefixed).

        Because real RFC obsoletion is many-to-many, ``history`` legitimately
        BRANCHES -- this returns the whole connected component as a list of
        per-node summaries (each node's own direct obsoletes/obsoleted_by
        neighbors) rather than forcing a single linear path.

        ``status``:
          * ``"dangling"``  -- ``rfc_id`` was never seen as its own EntityRef
            (known only because something else's obsoletes/obsoleted_by
            pointed at it).
          * ``"obsoleted"`` -- some real node has an ``obsoletes`` edge
            targeting ``rfc_id``.
          * ``"current"``   -- seen directly, and nothing obsoletes it.
        """
        node_id = f"rfc:{rfc_id}"
        node = self.nodes.get(node_id)
        component = self._obsoletes_component(node_id)

        obsoletes_of: dict[str, set[str]] = {}
        obsoleted_by_of: dict[str, set[str]] = {}
        for e in self.edges:
            if e.edge_type != "obsoletes":
                continue
            obsoletes_of.setdefault(e.src, set()).add(e.dst)
            obsoleted_by_of.setdefault(e.dst, set()).add(e.src)

        history = [
            {
                "rfc": n[len("rfc:"):],
                "obsoletes": sorted(x[len("rfc:"):] for x in obsoletes_of.get(n, ())),
                "obsoleted_by": sorted(x[len("rfc:"):] for x in obsoleted_by_of.get(n, ())),
            }
            for n in sorted(component)
        ]

        if node is None or not node.seen_as_primary:
            status = "dangling"
        elif obsoleted_by_of.get(node_id):
            status = "obsoleted"
        else:
            status = "current"

        return {"history": history, "status": status}

    def get_corrections(self, rfc_id: str) -> list[str]:
        """Bare errata ids (e.g. ``"ERRX100"``, not ``"errata:ERRX100"``) whose
        ``corrects`` edge targets ``rfc:<rfc_id>``, sorted for determinism.
        """
        node_id = f"rfc:{rfc_id}"
        return sorted(
            e.src[len("errata:"):]
            for e in self.edges
            if e.edge_type == "corrects" and e.dst == node_id
        )
