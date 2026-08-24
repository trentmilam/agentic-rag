"""pytest bootstrap: puts the linkgraph repo root and the sibling ``graphrx``
repo root on ``sys.path`` once per test session (mirrors ``linkgraph/_paths.py``
and ``eval.py``'s own bootstrap)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from linkgraph._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()

import pytest  # noqa: E402

from linkgraph import community, fixtures, resolve  # noqa: E402


@pytest.fixture
def graph():
    """A fresh LinkGraph built from the hand-authored fixture, communities
    assigned. Fresh per-test (LinkGraph is mutable) rather than session-scoped."""
    g = resolve.build_graph(fixtures.FIXTURE_ENTITY_REFS)
    community.assign_communities(g)
    return g
