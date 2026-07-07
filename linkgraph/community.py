"""linkgraph's own community-assignment pass.

``graphrx`` (the sibling structural linter) has NO community-detection code of
its own -- ``graphrx.graph.community_members()`` only GROUPS nodes by a
``community`` label that must already be assigned (see that module's
docstring). Populating that label meaningfully is this repo's job.

Choice: connected components over the UNDIRECTED ``obsoletes``/``updates``/
``corrects`` subgraph (``co_mentions`` alone is excluded). Rationale: a family
of RFCs that supersede/update one another is this domain's real, unambiguous
lineage grouping -- the natural notion of "these documents belong together".
An erratum's ``corrects`` edge is just as unambiguous: an erratum exists
*because of* one specific RFC, so it belongs to that RFC's community rather
than sitting in a singleton of its own -- there is no real question of
"which lineage" the way there might be for a weaker signal. ``co_mentions``
IS excluded: two entities can appear in the same source document without
being topically related at all, so it is deliberately too noisy to define
community membership from.
"""
from __future__ import annotations

from .graph import LinkGraph

_COMMUNITY_EDGE_TYPES = {"obsoletes", "updates", "corrects"}


def assign_communities(graph: LinkGraph) -> dict[str, int]:
    """Assign every node a component id (mutates ``graph.nodes[*].community``
    in place) and return the ``node_id -> community_id`` mapping.

    Deterministic: components are found via sorted-order traversal (mirroring
    ``graphrx.graph.components()``'s own style) and numbered by the sorted
    order of their smallest member id, so re-running on a re-ordered input
    stream yields identical ids.
    """
    adj: dict[str, set[str]] = {n: set() for n in graph.nodes}
    for e in graph.edges:
        if e.edge_type not in _COMMUNITY_EDGE_TYPES:
            continue
        adj[e.src].add(e.dst)
        adj[e.dst].add(e.src)

    seen: set[str] = set()
    components: list[list[str]] = []
    for start in sorted(graph.nodes):
        if start in seen:
            continue
        stack = [start]
        comp: set[str] = set()
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            comp.add(u)
            stack.extend(sorted(adj[u] - seen))
        components.append(sorted(comp))

    assignment: dict[str, int] = {}
    for community_id, comp in enumerate(sorted(components, key=lambda c: c[0])):
        for node_id in comp:
            assignment[node_id] = community_id

    for node_id, community_id in assignment.items():
        graph.nodes[node_id].community = community_id

    return assignment
