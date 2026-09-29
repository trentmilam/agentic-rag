"""Sibling-path bootstrap.

linkgraph is not standalone: it hands its export off to ``graphrx`` (the
GraphRAG structural linter), which lives in its own git repo,
``rag-reliability``, cloned as a sibling directory next to this repo's own
root rather than nested inside it (see ``PROJECTS_ROOT`` below). It is not
pip-installed; it's imported by putting its repo ROOT (the directory that
CONTAINS the ``graphrx/`` package, not the package dir itself) on
``sys.path``, the same convention ``graphrx/eval.py`` itself uses to make
``import graphrx`` resolve from outside the package. rag-reliability is the
only repository still reached this way; the tools that used to sit beside
linkgraph as separate repositories are packages of this repository now.

This repo's own ``pytest``/stdlib deps are pip-installed via the repo root's
``pip install -e .``, into the repo's own shared venv; no sys.path entry is
needed for those.

Every linkgraph entry file (``eval.py``, ``tests/conftest.py``) calls
:func:`add_sibling_paths` first, before importing anything from ``graphrx``.
Idempotent: safe to call repeatedly in one process.
"""
from __future__ import annotations

import os
import sys

LINKGRAPH_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(LINKGRAPH_ROOT))
PROJECTS_ROOT = os.path.dirname(REPO_ROOT)
# NOTE ON DEPTH: this tool now lives at <repo>/packages/<name>/, two levels below the
# repo root, so PROJECTS_ROOT is resolved from there rather than from a sibling-of-the
# repo layout. consilium / ragpack / linkgraph / activerag / chainrag are NOT resolved
# here any more; they are packages of this repo, mapped by pyproject.toml's
# package-dir and importable after `pip install -e .`. The only thing left below is
# rag-reliability, which is a genuinely separate project; packaging it so it can be a
# declared dependency instead of a path is the remaining follow-up.


GRAPHRX_ROOT = os.path.join(PROJECTS_ROOT, "rag-reliability", "graphrx")

_SIBLING_ROOTS = [LINKGRAPH_ROOT, GRAPHRX_ROOT]


def add_sibling_paths() -> None:
    """Insert every sibling repo root at the front of ``sys.path`` (skipping
    any already present). Call before importing anything from ``graphrx``."""
    for root in _SIBLING_ROOTS:
        if root not in sys.path:
            sys.path.insert(0, root)
