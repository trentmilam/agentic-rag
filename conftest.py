"""pytest collection bootstrap.

Makes agentic-rag and its sibling repos importable for the whole test session,
regardless of test order or which subset is selected. Without this,
``pytest eval/test_supersession_cycle_safety.py`` on its own fails to collect
(``ModuleNotFoundError: No module named 'consilium'``): that test file only adds
the repo root to ``sys.path``, and the ``consilium`` import it transitively needs
happens to be satisfied only because another test collected earlier already ran
``add_sibling_paths()``. Doing it here, at the pytest rootdir, makes every clone
collect identically no matter what is run.

Paired with ``pyproject.toml``'s ``[tool.pytest.ini_options]`` (which pins the
rootdir to this repo) so pytest never inherits an unrelated ancestor directory's
pytest config on a different machine.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agenticrag._paths import add_sibling_paths  # noqa: E402

add_sibling_paths()


# ---------------------------------------------------------------------------
# Clean-clone guard.
#
# agentic-rag is not standalone: it imports the consilium and linkgraph sibling
# repos via sys.path and installs RAGpack editable (see the README "Honest
# scope"). With none of those present -- which is what `git clone && pytest`
# gives you, the first thing anyone tries -- four test modules used to raise
# during COLLECTION, so pytest aborted before running a single test and the
# only output was a ModuleNotFoundError traceback.
#
# Skipping them instead lets the corpus-free suite run and prints exactly what
# is missing and why. CI installs the real siblings, so nothing is skipped
# there and the integration stays genuinely covered.
# ---------------------------------------------------------------------------
import importlib.util  # noqa: E402

_SIBLING_DEPENDENT = {
    "tests/test_bootstrap.py": ("ragpack", "consilium"),
    "tests/test_qdrant_retrieval.py": ("consilium",),
    "tests/test_registry_loader.py": ("consilium",),
    "eval/test_supersession_cycle_safety.py": ("consilium",),
    "agenticrag/mcp/test_server.py": ("consilium",),
}

_CLONE_HINT = {
    "consilium": "git clone https://github.com/trentmilam/consilium ../consilium",
    "linkgraph": "git clone https://github.com/trentmilam/linkgraph ../linkgraph",
    "ragpack": "git clone https://github.com/trentmilam/RAGpack ../RAGpack "
               "&& pip install -e ../RAGpack",
}


def _missing(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is None
    except (ImportError, ValueError):
        return True


collect_ignore = []
_absent = set()
for _path, _needs in _SIBLING_DEPENDENT.items():
    _gone = [m for m in _needs if _missing(m)]
    if _gone:
        collect_ignore.append(_path)
        _absent.update(_gone)

if _absent:
    print(
        "\n[agentic-rag] skipping "
        + f"{len(collect_ignore)} sibling-dependent test module(s); missing: "
        + ", ".join(sorted(_absent))
        + "\n[agentic-rag] to run them:\n    "
        + "\n    ".join(_CLONE_HINT[m] for m in sorted(_absent))
        + "\n"
    )
