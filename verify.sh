#!/usr/bin/env bash
# POSIX equivalent of verify.bat (macOS/Linux): the fast, corpus-free quick-verify
# (unit tests + MCP tool wrappers + supersession cycle-safety; no corpus needed).
# The corpus-dependent evals are the separate "Full verify" in the README.
set -euo pipefail
cd "$(dirname "$0")"
PYTHONIOENCODING=utf-8 .venv/bin/python scripts/verify.py
