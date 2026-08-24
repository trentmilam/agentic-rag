"""Sibling-path bootstrap.

linkgraph is deliberately NOT standalone: it hands its export off to
``graphrx`` (the GraphRAG structural linter), living as a SIBLING directory
under the same ``projects/`` root (``rag-reliability/graphrx``), its own git
repo. It is not pip-installed; it's imported by putting its repo ROOT (the
directory that CONTAINS the ``graphrx/`` package, not the package dir itself)
on ``sys.path`` -- the same convention agentic-rag's ``agenticrag/_paths.py``
and chain-rag's ``chainrag/_paths.py`` already established for their own
sibling repos, and the one ``graphrx/eval.py`` itself uses to make
``import graphrx`` resolve from outside the package.

(Unlike ``graphrx``, this repo's own ``pytest``/stdlib deps are pip-installed
into linkgraph's own venv -- no sys.path entry needed for those.)

Every linkgraph entry file (``eval.py``, ``tests/conftest.py``) calls
:func:`add_sibling_paths` first, before importing anything from ``graphrx``.
Idempotent -- safe to call repeatedly in one process.
"""
from __future__ import annotations

import os
import sys

LINKGRAPH_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_ROOT = os.path.dirname(LINKGRAPH_ROOT)

GRAPHRX_ROOT = os.path.join(PROJECTS_ROOT, "rag-reliability", "graphrx")

_SIBLING_ROOTS = [LINKGRAPH_ROOT, GRAPHRX_ROOT]


def add_sibling_paths() -> None:
    """Insert every sibling repo root at the front of ``sys.path`` (skipping
    any already present). Call before importing anything from ``graphrx``."""
    for root in _SIBLING_ROOTS:
        if root not in sys.path:
            sys.path.insert(0, root)
