"""agenticrag.mcp: an additive MCP server surface over agentic-rag's real
answer path.

Importing this subpackage is side-effect-free and does NOT require the ``mcp``
package or a live Qdrant store: the tool *logic* is plain functions in
:mod:`agenticrag.mcp.server`, and the ``mcp`` wiring is imported lazily only when
the server is actually run (``python -m agenticrag.mcp.server``).
"""
from __future__ import annotations

from agenticrag.mcp.server import (
    RagContext,
    tool_get_corrections,
    tool_get_obsoletion_chain,
    tool_get_related,
    tool_search,
)

__all__ = [
    "RagContext",
    "tool_search",
    "tool_get_related",
    "tool_get_obsoletion_chain",
    "tool_get_corrections",
]
