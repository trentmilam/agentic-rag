"""Sibling-path bootstrap.

activerag reuses the ``headroom`` hardware-aware budget governor (``Headroom`` /
``GpuProfile`` / ``Decision``) that lives in the sibling repo ``rag-reliability``
under the same ``projects/`` root -- its own git repo, not pip-installed. This is
the same convention agentic-rag's ``agenticrag/_paths.py`` and linkgraph's
``linkgraph/_paths.py`` already established for THEIR sibling repos.

There is one structural difference from those two, and it is the whole reason
this module exists as its own file rather than a one-liner:

    ``graphrx``/``consilium`` are packages -- a directory that CONTAINS a
    ``graphrx/``/``consilium/`` sub-package (with ``__init__.py``). Those
    bootstraps therefore add the repo ROOT (the parent of the package) so that
    ``import graphrx`` / ``import consilium`` resolves the sub-package.

    ``rag-reliability/headroom`` is NOT a package -- it is a FLAT module
    directory with no ``__init__.py``: ``headroom.py``, ``loop.py``,
    ``embedder.py``, ``baselines.py``, ``eval.py`` all live directly in it. So
    to make ``import headroom`` resolve the flat ``headroom.py`` module, the
    directory that must go on ``sys.path`` is the ``headroom/`` directory
    ITSELF, not its parent. (Its parent would only expose a ``headroom``
    package, which does not exist here.)

activerag's own package is importable via the ``pythonpath = ["."]`` entry in
``pyproject.toml`` when running under pytest; ``ACTIVERAG_ROOT`` is added here
too so a non-pytest entry file (a future ``orchestrator.py`` run directly) can
also ``import activerag`` after calling :func:`add_sibling_paths`.

Every activerag entry point that touches ``headroom`` calls
:func:`add_sibling_paths` first, before importing it. Idempotent -- safe to call
repeatedly in one process.
"""
from __future__ import annotations

import os
import sys

ACTIVERAG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_ROOT = os.path.dirname(ACTIVERAG_ROOT)

# The FLAT module directory itself (contains headroom.py directly, no
# __init__.py) -- so ``import headroom`` resolves headroom.py, not a package.
HEADROOM_DIR = os.path.join(PROJECTS_ROOT, "rag-reliability", "headroom")

_SIBLING_PATHS = [ACTIVERAG_ROOT, HEADROOM_DIR]


def add_sibling_paths() -> None:
    """Insert every sibling path at the front of ``sys.path`` (skipping any
    already present). Call before importing ``headroom``."""
    for path in _SIBLING_PATHS:
        if path not in sys.path:
            sys.path.insert(0, path)
