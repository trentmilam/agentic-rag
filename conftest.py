"""pytest collection bootstrap.

Puts the repo root on ``sys.path`` so ``agenticrag`` / ``corpus_fetch`` / ``ingest``
import without an install, and fails with a useful message rather than a bare
``ModuleNotFoundError`` if the merged packages under ``packages/`` are not installed.

This file used to do considerably more. agentic-rag imported ``consilium`` and
``linkgraph`` from sibling repositories by inserting their roots on ``sys.path``, and
required ``RAGpack`` pip-installed editable from a third. Those repos now live under
``packages/`` here, mapped to their import names by ``pyproject.toml``'s
``package-dir``, so ``pip install -e .`` is the whole bootstrap and there is no
sibling layout to get wrong.

Paired with ``pyproject.toml``'s ``[tool.pytest.ini_options]`` (which pins the rootdir
to this repo) so pytest never inherits an unrelated ancestor directory's pytest config
on a different machine.
"""
import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Every package that lives under packages/ and is reachable only via the editable
# install. A missing one means `pip install -e .` has not been run -- say so once,
# clearly, instead of letting each test module raise its own ModuleNotFoundError.
_MERGED = ("consilium", "ragpack", "linkgraph", "activerag", "chainrag")


def _diagnose(name: str) -> str:
    """Return "" if ``name`` resolves to a real package inside THIS repository, or a
    description of what is wrong otherwise.

    Two distinct failures, both of which produce a green test run against code that is
    not the code in this checkout:

    * An implicit namespace package has a spec but no ``origin`` -- what a bare
      directory of the same name produces. This repo hit exactly that when the merged
      packages sat at the top level and shadowed themselves.
    * A spec whose ``origin`` points somewhere else -- a leftover editable install still
      aimed at the old separate repository next door. That one is worse: it is a real,
      importable, plausible-looking package, so the suite passes green against source
      that is not the source being edited. It is how this repo's own first post-merge
      run was measured, against the ragpack checkout one directory over.
    """
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return "not importable"
    if spec is None:
        return "not importable"
    if spec.origin is None:
        return "resolves to a namespace package (a bare directory is shadowing it)"
    origin = os.path.abspath(spec.origin)
    if not origin.startswith(_REPO_ROOT + os.sep):
        return "resolves OUTSIDE this repo, to " + origin
    return ""


_broken = [(n, why) for n in _MERGED for why in (_diagnose(n),) if why]
if _broken:
    pytest.exit(
        "the merged packages under packages/ are not resolving to this checkout:\n"
        + "\n".join("  {}: {}".format(n, why) for n, why in _broken)
        + "\nIf any of those name an old sibling checkout, uninstall it first"
          " (`pip uninstall -y " + " ".join(n for n, _ in _broken) + "`), then run"
          " `pip install -e .` from the repo root -- pyproject.toml maps each name"
          " into packages/.",
        returncode=4,
    )
