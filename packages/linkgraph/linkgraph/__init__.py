"""linkgraph -- a cross-document relationship graph over agentic-rag's entity
mentions: RFC obsoletes/updates supersession (real many-to-many), errata
corrections, and scored co-mention edges. Pure stdlib. Deterministic. Offline.
Hands off to the sibling ``graphrx`` structural linter (see ``adapter.py``).
"""
from .contract import EntityRef  # noqa: F401
from .graph import Edge, LinkGraph, Node  # noqa: F401
from .resolve import build_graph  # noqa: F401
from .community import assign_communities  # noqa: F401
from .scoring import co_mention_scores  # noqa: F401
from .adapter import export_graphrx_graph, load_from_export  # noqa: F401
