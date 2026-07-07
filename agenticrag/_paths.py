"""Sibling-path bootstrap.

agentic-rag is deliberately NOT standalone: it reuses two sibling capability
repos as libraries (their own instances), each living as a SIBLING directory
under the same ``projects/`` root, each its own git repo, neither pip-installed
-- each imported by putting its root on ``sys.path``:

* ``consilium`` -- the routing / citation-gating spine. A hard requirement of
  every entrypoint (``app.py``, ``run_demo.py``, the eval, the MCP server).
* ``linkgraph`` -- the cross-document relationship graph. A hard requirement
  only of the MCP server's relationship tools (``agenticrag.relationships``);
  the chat UI, demo, and eval never import it.

(RAGpack, unlike these two, IS pip-installed editable into agentic-rag's own
venv -- ``import ragpack`` needs no sys.path entry here.)

Every agentic-rag entry file calls :func:`add_sibling_paths` first, before
importing anything from a sibling repo. Idempotent -- safe to call repeatedly in
one process.
"""
from __future__ import annotations

import os
import sys

AGENTIC_RAG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_ROOT = os.path.dirname(AGENTIC_RAG_ROOT)

CONSILIUM_ROOT = os.path.join(PROJECTS_ROOT, "consilium")
LINKGRAPH_ROOT = os.path.join(PROJECTS_ROOT, "linkgraph")

_SIBLING_ROOTS = [AGENTIC_RAG_ROOT, CONSILIUM_ROOT, LINKGRAPH_ROOT]


def add_sibling_paths() -> None:
    """Insert every sibling repo root at the front of ``sys.path`` (skipping any
    already present). Call before importing anything from a sibling repo."""
    for root in _SIBLING_ROOTS:
        if root not in sys.path:
            sys.path.insert(0, root)


# The exact sibling commits this release was verified against (also recorded in
# requirements.txt). Named in the mismatch errors below so a divergent checkout
# points at a concrete, checkoutable anchor rather than "some other version."
_VERIFIED_SIBLINGS = "consilium@5228cbb, linkgraph@46bdd04, RAGpack@a0078fb"


def verify_sibling_api() -> None:
    """Assert the *present* consilium sibling exposes the exact API agentic-rag
    calls -- not merely that *a* consilium is importable.

    ``add_sibling_paths`` plus the module-level ``from consilium... import`` lines
    already fail loudly when a sibling is MISSING or a symbol was renamed/removed.
    They do NOT catch a *present-but-divergent* checkout whose symbols still exist
    but whose call contract has drifted -- which would otherwise fail deep inside a
    query with an opaque ``TypeError``. This checks that contract once, up front,
    with a message naming the verified commit to check out. Cheap (signature
    introspection only), so the single query funnel (``build_registry``) calls it.
    """
    add_sibling_paths()
    import inspect

    try:
        from consilium.compute import ComputeModule, answer_v3
        from consilium.module import Chunk, Descriptor, Module
        from consilium.registry import Registry
        from consilium.router import Router
    except ImportError as exc:  # a symbol this repo relies on was renamed/removed
        raise ImportError(
            "A required symbol is missing from the consilium sibling checkout next to "
            "this repo -- it is present but divergent from the verified release "
            f"({_VERIFIED_SIBLINGS}). Re-clone/checkout that commit. Underlying: {exc}"
        ) from exc

    # answer_v3 is called positionally as answer_v3(query, registry, embedder, router).
    answer_params = list(inspect.signature(answer_v3).parameters)
    if answer_params[:4] != ["query", "registry", "embedder", "router"]:
        raise RuntimeError(
            "consilium.compute.answer_v3's signature has drifted from the verified "
            f"release ({_VERIFIED_SIBLINGS}): expected (query, registry, embedder, "
            f"router, ...), got {tuple(answer_params)}. Check out the verified commit."
        )

    # Router is constructed with these calibration kwargs (see bootstrap.ROUTER_KWARGS).
    router_params = inspect.signature(Router.__init__).parameters
    for kwarg in ("floor", "anchor_centroid", "anchor_best_chunk"):
        if kwarg not in router_params:
            raise RuntimeError(
                f"consilium.router.Router no longer accepts the {kwarg!r} calibration "
                "kwarg this repo relies on -- the consilium checkout has drifted from "
                f"the verified release ({_VERIFIED_SIBLINGS}). Check out that commit."
            )

    # These are all used as base classes / data holders; a non-class here means a
    # divergent consilium replaced the type this repo subclasses or constructs.
    for cls in (ComputeModule, Registry, Chunk, Descriptor, Module):
        if not isinstance(cls, type):
            raise RuntimeError(
                f"consilium exposes {cls!r} as a non-class -- the checkout has drifted "
                f"from the verified release ({_VERIFIED_SIBLINGS}). Check out that commit."
            )
