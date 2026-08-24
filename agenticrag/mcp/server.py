"""agentic-rag MCP server -- exposes the repo's real RAG answer path as MCP tools.

Additive scaffold: this module adds an MCP surface *on top of* the existing
answer path (``consilium.compute.answer_v3`` over agentic-rag's own Qdrant-backed
Registry, exactly as ``app.py`` wires it). It changes nothing about how answers
are computed -- ``search`` is a thin, faithful wrapper.

Layering (deliberate, so this file is importable/unit-testable *without* the
``mcp`` package installed and *without* ever opening Qdrant):

* Module top level imports nothing heavy -- only the sibling-path bootstrap. In
  particular it does NOT ``import mcp`` and does NOT build the Registry. Importing
  this module must never touch Qdrant (agentic-rag's local-mode store may be held
  open by a concurrent eval run; a second opener crashes both).
* The tool *logic* lives in plain functions (``tool_search`` / ``tool_get_related``
  / ``tool_get_obsoletion_chain`` / ``tool_get_corrections``) that take an explicit
  context. Tests drive these directly with hand-built fakes.
* The real embedder/Registry/Router are built exactly once, at *server startup*,
  inside :func:`build_context` (mirroring ``app.py``'s module-level EMBEDDER/
  REGISTRY/ROUTER pattern -- but here it is startup-time, never import-time).
* The ``mcp`` wiring lives entirely inside :func:`main`, imported lazily. ``mcp``
  is not yet a dependency of this repo (see the note in :func:`main`).

Transport decision (documented; no precedent in this repo cluster either way):
**stdio** -- the simplest transport for a single-user local demo. The MCP client
launches this process and speaks the protocol over stdin/stdout; no port, no
network listener, no auth surface. If a multi-client or remote deployment is ever
needed, FastMCP also offers HTTP/SSE transports; revisit then. Flagged for review.
"""
from __future__ import annotations

from dataclasses import dataclass


# The one hint every not-yet-wired relationship tool hands back, so a caller who
# hits the un-built bridge is steered to the tool that *does* answer today.
_FALLBACK_HINT = "use search for direct obsoletion questions"


@dataclass
class RagContext:
    """The three long-lived objects the answer path needs, built once and reused
    for every ``search`` call (never per-call). Mirrors ``app.py``'s
    module-level ``EMBEDDER`` / ``REGISTRY`` / ``ROUTER`` trio."""
    registry: object
    embedder: object
    router: object


def build_context() -> RagContext:
    """Build the real embedder + Qdrant-backed Registry + Router **once**, at
    server startup. Mirrors ``app.py`` lines 38-40 exactly.

    WARNING: this opens the real embedder and the shared Qdrant collection. Call
    it only from real server startup (:func:`main`). Never call it from a unit
    test -- the tests build a :class:`RagContext` from fakes instead.
    """
    from agenticrag.bootstrap import build_registry, build_router
    from agenticrag.embed_config import get_embedder

    embedder = get_embedder()
    registry = build_registry(embedder)
    router = build_router(registry, embedder)
    return RagContext(registry=registry, embedder=embedder, router=router)


# ---------------------------------------------------------------------------
# Tool logic (pure; no mcp dependency; unit-tested against fakes)
# ---------------------------------------------------------------------------

def tool_search(query: str, ctx: RagContext) -> dict:
    """Answer a natural-language query over the real IETF RFC/errata/IANA corpus.

    A thin, faithful wrapper over ``consilium.compute.answer_v3`` -- the exact
    call ``app.py`` makes. Its return dict is passed back **verbatim**, including
    an honest ``{"kind": "abstain", ...}`` result: an abstain means nothing in the
    corpus supported an answer, and it must never be papered over here.
    """
    from consilium.compute import answer_v3

    return answer_v3(query, ctx.registry, ctx.embedder, ctx.router)


def _call_bridge(tool: str, fn_name: str, *args, **kwargs) -> dict:
    """Dispatch to ``agenticrag.relationships`` -- a real, working linkgraph-backed
    bridge (verified against real IETF RFC/errata/IANA data; no Qdrant dependency,
    reads ``data/entities/candidates.jsonl`` directly).

    Returns ONE stable dict shape either way, so an MCP client parses the same
    envelope on success and failure (the underlying bridge functions return bare
    ``list``s / ``dict``s of differing shapes -- wrapping them here is what makes
    every relationship tool's declared ``-> dict`` contract honest):

    * success  -> ``{"ok": True,  "tool": <tool>, "result": <bridge return>}``
    * failure  -> ``{"ok": False, "tool": <tool>, "error": ..., "fallback": ...}``

    The lazy import + defensive guards stay regardless: if that module isn't
    importable, doesn't expose ``fn_name``, or the call raises, return the failure
    envelope instead of propagating -- one broken tool must never crash the server.
    """
    try:
        from agenticrag import relationships
    except Exception as exc:  # ImportError today; guard anything a half-built module raises
        return _bridge_unavailable(tool, f"agenticrag.relationships not importable yet ({exc!r})")

    fn = getattr(relationships, fn_name, None)
    if not callable(fn):
        return _bridge_unavailable(tool, f"agenticrag.relationships.{fn_name} not implemented yet")

    try:
        result = fn(*args, **kwargs)
    except Exception as exc:
        return _bridge_unavailable(tool, f"agenticrag.relationships.{fn_name} raised {exc!r}")
    return {"ok": True, "tool": tool, "result": result}


def _bridge_unavailable(tool: str, reason: str) -> dict:
    """The documented degraded-but-honest shape returned when the relationships
    bridge can't serve a call yet."""
    return {"ok": False, "tool": tool, "error": reason, "fallback": _FALLBACK_HINT}


def tool_get_related(entity_id: str, max_hops: int = 1, min_score: float = 0.0,
                     edge_types=None) -> dict:
    """Neighbours of ``entity_id`` in the relationship graph, via the real
    ``agenticrag.relationships.get_related`` passthrough to ``LinkGraph``.

    ``entity_id`` must be a FULL node id (e.g. ``"rfc:RFC2616"`` or
    ``"errata:1483"``), matching ``relationships.get_related``'s own contract --
    unlike ``rfc_id`` in :func:`tool_get_obsoletion_chain`/
    :func:`tool_get_corrections` below, which take a bare id.

    On success returns ``{"ok": True, "tool": "get_related", "result": [...]}``
    where ``result`` is a list of ``(node_id, hop_distance)`` pairs; if the bridge
    is ever unimportable or raises, returns the failure envelope (``ok: False`` +
    a hint to use ``search``) instead of propagating."""
    return _call_bridge("get_related", "get_related", entity_id,
                        max_hops=max_hops, min_score=min_score, edge_types=edge_types)


def tool_get_obsoletion_chain(rfc_id: str) -> dict:
    """The Obsoletes/Obsoleted-by chain for ``rfc_id``, via the real
    ``agenticrag.relationships.get_obsoletion_chain`` passthrough to
    ``LinkGraph`` (built from the real IETF candidates.jsonl corpus).

    ``rfc_id`` is a BARE RFC id (e.g. ``"RFC2616"``, no ``rfc:`` prefix).

    On success returns ``{"ok": True, "tool": "get_obsoletion_chain", "result":
    {"history": [...], "status": ...}}``; if the bridge is ever unimportable or
    raises, returns the failure envelope -- and the hint is exactly right here:
    ``search`` also answers direct obsoletion questions via the deterministic
    supersession module."""
    return _call_bridge("get_obsoletion_chain", "get_obsoletion_chain", rfc_id)


def tool_get_corrections(rfc_id: str) -> dict:
    """The errata/corrections attached to ``rfc_id``, via the real
    ``agenticrag.relationships.get_corrections`` passthrough to ``LinkGraph``.

    ``rfc_id`` is a BARE RFC id (e.g. ``"RFC2616"``, no ``rfc:`` prefix).

    On success returns ``{"ok": True, "tool": "get_corrections", "result": [...]}``
    where ``result`` is a list of bare errata ids; if the bridge is ever
    unimportable or raises, returns the failure envelope."""
    return _call_bridge("get_corrections", "get_corrections", rfc_id)


# ---------------------------------------------------------------------------
# MCP wiring (lazy; only touched when actually serving)
# ---------------------------------------------------------------------------

def main() -> None:
    """Build the context once and serve the four tools over stdio.

    Verified against the real installed SDK (``mcp==1.28.1``, see
    ``agenticrag/requirements.txt``): ``FastMCP(name)``, the ``@server.tool()``
    decorator, and ``server.run(transport="stdio")`` all match its real API
    (checked via ``inspect.signature`` and a live tool-registration smoke test --
    no live Qdrant/embedder needed for that check). The import stays lazy here
    regardless, so the tool logic and its tests keep running with ``mcp`` absent
    if it's ever uninstalled.

    (The subpackage is named ``agenticrag.mcp``; ``from mcp...`` below is an
    absolute import and resolves to the installed top-level ``mcp`` SDK, not this
    subpackage -- worth re-confirming once the SDK is actually installed.)

    Tools deliberately NOT exposed: ``export_graphrx_graph`` (a different
    downstream consumer's interchange format) and raw ``Router.route`` (an internal
    ranking signal, not an answer).
    """
    from mcp.server.fastmcp import FastMCP

    ctx = build_context()
    server = FastMCP("agentic-rag")

    @server.tool()
    def search(query: str) -> dict:
        """Cited, extractive answer over the real IETF RFC/errata/IANA corpus (or
        an honest abstain). Wraps agentic-rag's real answer path verbatim."""
        return tool_search(query, ctx)

    @server.tool()
    def get_related(entity_id: str, max_hops: int = 1, min_score: float = 0.0,
                    edge_types: list | None = None) -> dict:
        """Graph neighbours of an entity (full node id, e.g. ``"rfc:RFC2616"``)."""
        return tool_get_related(entity_id, max_hops, min_score, edge_types)

    @server.tool()
    def get_obsoletion_chain(rfc_id: str) -> dict:
        """Obsoletes/Obsoleted-by chain for an RFC (bare id, e.g. ``"RFC2616"``)."""
        return tool_get_obsoletion_chain(rfc_id)

    @server.tool()
    def get_corrections(rfc_id: str) -> dict:
        """Errata/corrections for an RFC (bare id, e.g. ``"RFC2616"``)."""
        return tool_get_corrections(rfc_id)

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
