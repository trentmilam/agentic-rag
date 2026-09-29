"""Sibling-path bootstrap.

activerag reuses the ``headroom`` hardware-aware budget governor (``Headroom`` /
``GpuProfile`` / ``Decision``) that lives in the sibling repo ``rag-reliability``,
next to the agentic-rag repo itself: its own git repo, not pip-installed. It is
the last such dependency: consilium, ragpack, linkgraph, activerag and chainrag
were all reached this way too and are packages of this repository now, so the
only bootstrap left here is the one for rag-reliability.

There is one structural difference between a package-shaped sibling and a flat
one, and it is the whole reason this module exists as its own file rather than
a one-liner:

    ``graphrx``/``consilium`` are packages: a directory that contains a
    ``graphrx/``/``consilium/`` sub-package (with ``__init__.py``). Those
    bootstraps therefore add the repo root (the parent of the package) so that
    ``import graphrx`` / ``import consilium`` resolves the sub-package.

    ``rag-reliability/headroom`` is not a package. It is a flat module
    directory with no ``__init__.py``: ``headroom.py``, ``loop.py``,
    ``embedder.py``, ``baselines.py``, ``eval.py`` all live directly in it. So
    to make ``import headroom`` resolve the flat ``headroom.py`` module, the
    directory that must go on ``sys.path`` is the ``headroom/`` directory
    itself, not its parent (its parent would only expose a ``headroom``
    package, which does not exist here).

activerag's own package is importable via the ``pythonpath = ["."]`` entry in
``pyproject.toml`` when running under pytest; ``ACTIVERAG_ROOT`` is added here
too so a non-pytest entry file (a future ``orchestrator.py`` run directly) can
also ``import activerag`` after calling :func:`add_sibling_paths`.

Every activerag entry point that touches ``headroom`` calls
:func:`add_sibling_paths` first, before importing it. Idempotent: safe to call
repeatedly in one process.
"""
from __future__ import annotations

import os
import sys

ACTIVERAG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(ACTIVERAG_ROOT))
PROJECTS_ROOT = os.path.dirname(REPO_ROOT)
# Note on depth: this tool now lives at <repo>/packages/<name>/, two levels below the
# repo root, so PROJECTS_ROOT is resolved from there rather than from a sibling-of-the
# repo layout. consilium / ragpack / linkgraph / activerag / chainrag are not resolved
# here any more; they are packages of this repo, mapped by pyproject.toml's
# package-dir and importable after `pip install -e .`. The only thing left below is
# rag-reliability, which is a genuinely separate project; packaging it so it can be a
# declared dependency instead of a path is the remaining follow-up.


# The flat module directory itself (contains headroom.py directly, no
# __init__.py), so ``import headroom`` resolves headroom.py, not a package.
HEADROOM_DIR = os.path.join(PROJECTS_ROOT, "rag-reliability", "headroom")

_SIBLING_PATHS = [ACTIVERAG_ROOT, HEADROOM_DIR]


def add_sibling_paths() -> None:
    """Insert every sibling path at the front of ``sys.path`` (skipping any
    already present). Call before importing ``headroom``."""
    for path in _SIBLING_PATHS:
        if path not in sys.path:
            sys.path.insert(0, path)
