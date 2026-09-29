#!/usr/bin/env python
"""Quick verify: agentic-rag's fast, corpus-free checks as one pass/fail command.

Runs the pytest suite configured in pyproject.toml: agentic-rag's own MCP
tool-wrapper, connector, registry-loader and bootstrap tests and the supersession
graph-walk cycle-safety suite, plus the shared pytest suites of four of the five
tools merged in under packages/ (consilium, ragpack, linkgraph, activerag;
chainrag has its own separate eval, not a shared pytest suite). None of these
need the ingested 321k-chunk corpus: they use small synthetic fixtures and a
fake Qdrant client, so this runs in seconds on a fresh clone once `pip install -r
requirements.txt` and `pip install -e .` are done.

Exits non-zero on the first failure, so CI and a human get one clear signal instead
of five separate manual commands. The corpus-dependent evals (eval_agenticrag.py,
prove_revision_guard.py) are NOT run here: they need the built corpus; see the
README "Full verify".

    python scripts/verify.py        # or: verify.bat
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print(f"[verify] agentic-rag quick verify (corpus-free) in {REPO_ROOT}", flush=True)
    # Run pytest from the repo root so it picks up pyproject.toml's rootdir/testpaths
    # and conftest.py's sibling-path bootstrap, identically to a bare `pytest` there.
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT)
    if result.returncode == 0:
        print("[verify] PASS -- all corpus-free checks green.", flush=True)
    else:
        print("[verify] FAIL -- see the pytest output above.", file=sys.stderr, flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
