"""Thin passthrough bridge from agentic-rag into linkgraph's real, tested
relationship graph (built from the same real candidates.jsonl the corpus's
own entity-extraction produced). Kept deliberately separate from
SupersessionModule -- both answer "what obsoleted RFC X" from independently
built sources over the same underlying IETF facts, kept separate on purpose so
they can be cross-checked against each other (e.g. RFC 2616's real 6-way
obsoletion into RFC 7230-7235 should agree in both).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from agenticrag._paths import add_sibling_paths

add_sibling_paths()

from linkgraph.adapter import load_from_export  # noqa: E402
from linkgraph.graph import LinkGraph  # noqa: E402
from linkgraph.resolve import build_graph  # noqa: E402

_AGENTIC_RAG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CANDIDATES_PATH = _AGENTIC_RAG_ROOT / "data" / "entities" / "candidates.jsonl"

_GRAPH: LinkGraph | None = None


def _graph() -> LinkGraph:
    """Build the single process-wide ``LinkGraph`` on first use and cache it.

    Deferred to first call (rather than import time) so importing this module
    never does file I/O -- it stays safe to import before an ingest has
    produced the file.
    """
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph(load_from_export(str(_DEFAULT_CANDIDATES_PATH)))
    return _GRAPH


def get_related(
    entity_id: str,
    max_hops: int = 1,
    min_score: float = 0.0,
    edge_types: Optional[Iterable[str]] = None,
) -> list[tuple[str, int]]:
    """Passthrough to ``LinkGraph.get_related`` (identical signature). ``entity_id``
    is a FULL node id, e.g. ``"rfc:RFC2616"``."""
    return _graph().get_related(entity_id, max_hops, min_score, edge_types)


def get_obsoletion_chain(rfc_id: str) -> dict:
    """Passthrough to ``LinkGraph.get_obsoletion_chain`` (identical signature).
    ``rfc_id`` is a BARE RFC id, e.g. ``"RFC2616"`` (no ``rfc:`` prefix)."""
    return _graph().get_obsoletion_chain(rfc_id)


def get_corrections(rfc_id: str) -> list[str]:
    """Passthrough to ``LinkGraph.get_corrections`` (identical signature).
    ``rfc_id`` is a BARE RFC id, e.g. ``"RFC2616"`` (no ``rfc:`` prefix)."""
    return _graph().get_corrections(rfc_id)
