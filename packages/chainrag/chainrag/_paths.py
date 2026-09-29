"""Sibling-path bootstrap.

chain-rag is not standalone: it reuses ``consilium`` (the routing/
citation-gating spine, as a library, own Registry instance, zero coupling to
any other Consilium instance) and 4 of ``rag-reliability``'s gate tools.
``consilium`` is a package of this same repository, resolved by the root
``pip install -e .``; ``rag-reliability`` is the one genuinely external
dependency, its own git repo, cloned next to the agentic-rag repo itself (see
the README) and imported by putting its root on ``sys.path``.

(RAGpack, like consilium, is a package of this repository and needs no
sys.path entry: ``import ragpack`` resolves after the root install.)

Every chain-rag entry file calls :func:`add_sibling_paths` first, before importing
anything from the rag-reliability sibling. Idempotent: safe to call repeatedly
in one process.
"""
from __future__ import annotations

import os
import sys

CHAIN_RAG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(CHAIN_RAG_ROOT))
PROJECTS_ROOT = os.path.dirname(REPO_ROOT)
# Note on depth: this tool now lives at <repo>/packages/<name>/, two levels below the
# repo root, so PROJECTS_ROOT is resolved from there rather than from a sibling-of-the
# repo layout. consilium / ragpack / linkgraph / activerag / chainrag are not resolved
# here any more; they are packages of this repo, mapped by pyproject.toml's
# package-dir and importable after `pip install -e .`. The only thing left below is
# rag-reliability, which is a genuinely separate project; packaging it so it can be a
# declared dependency instead of a path is the remaining follow-up.


RAG_RELIABILITY_ROOT = os.path.join(PROJECTS_ROOT, "rag-reliability")

# rag-reliability has no __init__.py anywhere; each tool is a flat module that
# imports its neighbors with bare `import <module>` (e.g. legigate.py does
# `from embed import cosine, embed`), so each tool's own subdir must be on
# sys.path individually, not just the rag-reliability root.
_RELIABILITY_TOOLS = ["vecstamp", "chunkledger", "plumbline", "legigate"]

_SIBLING_ROOTS = [
    CHAIN_RAG_ROOT,     # so `import chainrag` resolves for entry scripts
    *[os.path.join(RAG_RELIABILITY_ROOT, t) for t in _RELIABILITY_TOOLS],
]


def add_sibling_paths() -> None:
    """Insert every sibling repo root at the front of ``sys.path`` (skipping any
    already present). Call before importing anything from a sibling repo."""
    for root in _SIBLING_ROOTS:
        if root not in sys.path:
            sys.path.insert(0, root)
