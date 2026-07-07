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
