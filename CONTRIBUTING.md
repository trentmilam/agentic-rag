# Contributing to agentic-rag

Thanks for your interest. This is a portfolio project, but issues and PRs that
sharpen its correctness, honesty, or docs are welcome.

## Setup

Clone this repository and nothing else. It used to need four checkouts side by
side, because `consilium`, `linkgraph`, `RAGpack`, `activerag` and `chainrag` were
separate repositories reached over `sys.path`; they are packages of this one now,
under [`packages/`](packages/). Follow the [README "Quickstart"](README.md#quickstart)
for the Python 3.12 venv, `pip install -r requirements.txt && pip install -e .`, and
(only if you need the corpus-dependent paths) the corpus fetch + ingest.

One outside dependency is left: [`rag-reliability`](https://github.com/trentmilam/rag-reliability)
supplies `graphrx` and `headroom` to three of the merged packages, and is still
resolved by path. Cloning it beside this repo enables those integrations; without
it their tests skip locally. CI checks it out at a pinned commit and **fails if
those tests report skipped instead of passing**, so the integration cannot rot
behind a green badge.

## Verifying a change

Two tiers, both documented in the README:

- Quick verify (seconds, no corpus): `verify.bat` (or `python scripts/verify.py`,
  or just `pytest`). Runs the unit tests, the MCP tool-wrapper tests, and the
  supersession cycle-safety suite against small synthetic fixtures and a fake Qdrant
  client. This is what CI runs, and what every PR must keep green.
- Full verify (needs the ingested 321k-chunk corpus): `python eval/eval_agenticrag.py`.

Any change to retrieval, routing, the revision guard, or the supersession graph walk
should come with a corpus-free test (see `tests/`, `agenticrag/mcp/test_server.py`,
and `eval/test_supersession_cycle_safety.py` for the fixture-only style to match).

## House rules

- Cited or an honest abstain. The whole premise is no fabricated answers: a
  change that could let the answer path return an uncited or made-up claim is a
  regression even if every test still passes.
- Numbers are measured, not asserted. Any count or rate in code comments, docs, or
  a PR description must come from a real command's real output (see the errata
  disposition breakdown in `agenticrag/bootstrap.py` for the expected style).
- Match the surrounding code. No new dependency without a clear reason; keep the
  fixture-only, no-network, no-GPU discipline in tests.

## License

By contributing you agree your contributions are licensed under this project's
[MIT License](LICENSE).
