# Contributing to agentic-rag

Thanks for your interest. This is a portfolio project, but issues and PRs that
sharpen its correctness, honesty, or docs are welcome.

## Setup

agentic-rag is **not standalone** — it imports the `consilium` and `linkgraph`
sibling repos via `sys.path` and installs `RAGpack` editable. Follow the
[README "Quickstart"](README.md#quickstart) to clone all four side-by-side, create
the Python 3.12 venv, install the deps, and (only if you need the corpus-dependent
paths) fetch + ingest the corpus.

The exact sibling commits this release was verified against are pinned in
[`requirements.txt`](requirements.txt) and in [`.github/workflows/ci.yml`](.github/workflows/ci.yml);
`agenticrag/_paths.py::verify_sibling_api` fails loudly at registry-build time if the
`consilium` checkout next to you has drifted from the API this repo calls.

## Verifying a change

Two tiers, both documented in the README:

- **Quick verify** (seconds, no corpus): `verify.bat` (or `python scripts/verify.py`,
  or just `pytest`). Runs the unit tests, the MCP tool-wrapper tests, and the
  supersession cycle-safety suite against small synthetic fixtures and a fake Qdrant
  client. **This is what CI runs, and what every PR must keep green.**
- **Full verify** (needs the ingested 321k-chunk corpus): `python eval/eval_agenticrag.py`.

Any change to retrieval, routing, the revision guard, or the supersession graph walk
should come with a corpus-free test (see `tests/`, `agenticrag/mcp/test_server.py`,
and `eval/test_supersession_cycle_safety.py` for the fixture-only style to match).

## House rules

- **Cited or an honest abstain.** The whole premise is no fabricated answers — a
  change that could let the answer path return an uncited or made-up claim is a
  regression even if every test still passes.
- **Numbers are measured, not asserted.** Any count or rate in code comments, docs, or
  a PR description must come from a real command's real output (see the errata
  disposition breakdown in `agenticrag/bootstrap.py` for the expected style).
- **Match the surrounding code.** No new dependency without a clear reason; keep the
  fixture-only, no-network, no-GPU discipline in tests.

## License

By contributing you agree your contributions are licensed under this project's
[MIT License](LICENSE).
