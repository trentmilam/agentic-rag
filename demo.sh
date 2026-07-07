#!/usr/bin/env bash
# POSIX equivalent of demo.bat (macOS/Linux). Requires the corpus to have been
# built first (see the README "Quickstart"). CPU-fine for query; GPU only speeds
# up the one-time ingest. Paths are relative to this script.
set -euo pipefail
cd "$(dirname "$0")"
PYTHONIOENCODING=utf-8 .venv/bin/python run_demo.py
