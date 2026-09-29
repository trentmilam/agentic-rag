"""SupersessionModule: the real many-to-many RFC Obsoletes/Obsoleted-by graph,
exposed as a routable Consilium compute capability.

The retrieval modules (see bootstrap.py) cannot answer "what obsoleted RFC
2616?" the way an encyclopedic lookup can: RFC 2616's own full text is a real,
whole, unmodified document. There is no "current revision" of it, it was
entirely replaced by six different documents (RFC 7230-7235). The FACT of that
obsoletion lives in the real IETF Obsoletes/Obsoleted-by graph
(``data/entities/revisions.json``, built by
``ingest.connectors.rfc_index.build_revisions_index`` from the live
rfc-index.txt), not in any one chunk of prose. This module parses that graph
once at construction and answers deterministically: no LLM, no retrieval,
no guessing.
"""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path


from consilium.compute import ComputeModule  # noqa: E402

_AGENTIC_RAG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REVISIONS_PATH = _AGENTIC_RAG_ROOT / "data" / "entities" / "revisions.json"

_RFC_RE = re.compile(r"\bRFC\s*(\d+)\b", re.IGNORECASE)

# Defensive bound on total nodes _walk_supersession will visit. Real IETF
# obsoletion components are small (RFC 2616's own 6-successor case is among
# the largest observed in the live index), so this guards a hypothetical
# pathological or cyclic graph, not an expected real limit.
_MAX_WALK_NODES = 50


def _extract_rfc_key(query: str) -> str | None:
    """The first RFC number named in ``query``, formatted as the "RFC<n>" key
    ``data/entities/revisions.json`` is indexed by. ``None`` if no RFC number is
    named in the query at all."""
    match = _RFC_RE.search(query)
    if match is None:
        return None
    return f"RFC{int(match.group(1))}"


def _walk_supersession(start: str, graph: dict, *, max_nodes: int = _MAX_WALK_NODES) -> list[dict]:
    """Breadth-first walk of the many-to-many Obsoletes/Obsoleted-by graph, in
    both directions, starting at ``start``. Each node visited after ``start``
    is recorded once as ``{"rfc": <key>, "relation": "obsoletes"|"obsoleted_by",
    "hops": <int>}``. ``relation`` is the edge that reached it from ITS
    parent in the walk, not a global property of the node.

    Cycle-safe: a ``visited`` set means no node is ever re-queued, so a cyclic
    graph, never expected in real IETF data (an RFC cannot obsolete itself
    through a chain of real successors) but structurally possible in a
    hand-built graph, still terminates rather than looping forever; see the
    dedicated cycle-safety unit test (``eval/test_supersession_cycle_safety.py``).
    ``max_nodes`` bounds total visited nodes as a defensive cap (default 50),
    not an expected real limit.

    Real ``revisions.json`` entries store ``obsoletes``/``obsoleted_by`` as bare
    RFC-number ints (formatted here to "RFC<n>"); a synthetic test graph may
    instead store already-formatted string node names directly (e.g. "RFCX2")
    so a hand-built fixture never has to use a real-shaped "RFC<n>" id to
    assert something false about a real document; both forms are accepted.
    """
    if start not in graph:
        return []
    visited = {start}
    order: list[dict] = []
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, hops = queue.popleft()
        entry = graph.get(node) or {}
        for relation in ("obsoletes", "obsoleted_by"):
            for raw in entry.get(relation, []):
                neighbor = raw if isinstance(raw, str) else f"RFC{raw}"
                if neighbor in visited:
                    continue
                if len(visited) >= max_nodes:
                    continue  # defensive cap reached: stop admitting new nodes
                visited.add(neighbor)
                order.append({"rfc": neighbor, "relation": relation, "hops": hops + 1})
                queue.append((neighbor, hops + 1))
    return order


class SupersessionModule(ComputeModule):
    """Routable like any retrieval module (the router scores its descriptor the
    same way), but ``compute(query)`` parses an RFC number out of the query and
    looks it up in the real graph instead of retrieving text.

    Not a ``@dataclass`` subclass (unlike the library's own
    ``FinanceComputeModule``) because it needs one extra constructor argument
    (``revisions_path``) beyond the base's dataclass fields, hence the plain-
    class-calling-``super().__init__`` shape, the usual way a compute adapter
    carries constructor state the dataclass base doesn't declare.
    """

    def __init__(self, embedder, descriptor, revisions_path: str | Path | None = None):
        super().__init__(name=descriptor.name, descriptor=descriptor, embedder=embedder)
        path = Path(revisions_path) if revisions_path else _DEFAULT_REVISIONS_PATH
        self._revisions: dict = json.loads(path.read_text(encoding="utf-8"))

    def compute(self, query: str) -> dict:
        key = _extract_rfc_key(query)
        if key is None:
            return {"ok": False, "tool": "supersession", "error": "no RFC number found in query"}

        entry = self._revisions.get(key)
        if entry is None:
            status, successors = "not_found", []
        else:
            successors = [f"RFC{n}" for n in entry.get("obsoleted_by", [])]
            status = "obsoleted" if successors else "current"

        history = _walk_supersession(key, self._revisions)
        return {
            "ok": True,
            "tool": "supersession",
            "inputs": {"rfc": key},
            "method": "real IETF Obsoletes/Obsoleted-by graph walk (data/entities/revisions.json)",
            "deterministic": True,
            "result": {"history": history, "status": status, "successors": successors},
        }
