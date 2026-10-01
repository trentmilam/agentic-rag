# Contributing to agentic-rag

Issues and PRs on correctness and docs are welcome.

## Setup

- Clone this repo only; the merged tools live under [`packages/`](packages/)
- Follow the [README "Quickstart"](README.md#quickstart): Python 3.12 venv, `pip install -r requirements.txt && pip install -e .`
- Corpus fetch and ingest only for corpus-dependent paths
- [`rag-reliability`](https://github.com/trentmilam/rag-reliability) supplies `graphrx` and `headroom` to three packages, resolved by path
- Without it cloned beside this repo, those tests skip locally
- CI checks it out pinned and fails if those tests skip

## Verifying a change

- Quick verify (seconds, no corpus): `verify.bat`, `python scripts/verify.py`, or `pytest`. Every PR must keep it green.
- Full verify (needs the ingested corpus): `python eval/eval_agenticrag.py`

Changes to retrieval, routing, the revision guard or the supersession walk need a corpus-free test. Match `tests/`, `agenticrag/mcp/test_server.py`, `eval/test_supersession_cycle_safety.py`.

## House rules

- Cited or abstain. No uncited claims in the answer path.
- Numbers come from a real command's output (see the errata breakdown in `agenticrag/bootstrap.py`).
- Match surrounding code. No new dependency without a reason. Tests stay fixture-only, no network, no GPU.

## License

Contributions are licensed under the project's [MIT License](LICENSE).
