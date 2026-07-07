#!/usr/bin/env bash
# POSIX equivalent of app.bat (macOS/Linux). Query-time embedding is a single
# short string, so this runs fine on CPU with no GPU setup -- GPU only speeds up
# the one-time corpus INGEST (see the README "GPU note (ingest only)"). Paths are
# relative to this script, so it runs from any clone.
set -euo pipefail
cd "$(dirname "$0")"
PYTHONIOENCODING=utf-8 .venv/bin/python app.py
