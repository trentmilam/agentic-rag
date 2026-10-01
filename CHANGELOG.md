# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Standalone repo. `consilium`, `RAGpack`, `linkgraph`, `activerag` and `chain-rag` are now packages under `packages/`, merged with `git subtree` (histories kept). `git clone && pip install -e . && pytest` works from a bare checkout.
  - Deleted `agenticrag/_paths.py`, 22 `add_sibling_paths()` calls across 12 files, and `bootstrap.verify_sibling_api()`
  - Removed the three sibling commit-pin lists (`requirements.txt`, `_paths.py`, CI workflow)
  - `conftest.py` and CI refuse to run if a merged package resolves to a namespace package or a path outside the repo
  - `activerag.registry_bridge` no longer inserts a sibling `agentic-rag` checkout into `sys.path`
  - `activerag.refresh_hook` no longer derives its data directory from the repository's directory name
  - `rag-reliability` remains external (`graphrx`, `headroom`), used by three packages. CI pins it and fails if its tests skip
  - `pypdf` declared in `requirements.txt`
  - RAGpack's docTR/OCR CI job kept as its own job

- `ingest/run_ingest.py` prints progress: a start line (files found / changed), a heartbeat at most every 15s during embed/upsert, and the existing final JSON summary.

## [0.1.1]

- Re-pinned the linkgraph and RAGpack sibling checkouts (README quickstart, `requirements.txt`, CI) to reachable commits. The old pins were orphaned by a history rewrite.

## [0.1.0] - Initial public release

Cited, revision-aware retrieval over a 321,124-chunk IETF RFC corpus, with a deterministic supersession-graph lookup and an MCP server.

### Added
- Corpus fetch (`corpus_fetch/`): RFC full text, `rfc-index.txt` supersession graph, RFC errata, 7 IANA registries.
- Ingest (`ingest/`): per-source connectors that chunk, embed (`BAAI/bge-base-en-v1.5`) and load into local Qdrant, with an `is_current` flag from the obsoletion graph. `--recreate` rebuild and incremental path.
- Registry: 5-module Consilium registry (`rfc_text`, `rfc_index`, `errata`, `iana_registry`, `SupersessionModule`).
- Answer path: routed and citation-gated through `consilium`; cited answer or abstain, no LLM.
- MCP server (`agenticrag/mcp/server.py`): FastMCP over stdio, `search`, `get_obsoletion_chain`, `get_corrections`, `get_related`.
- Guards: embedder-consistency check (`verify_embedder_marker`), sibling API-shape check (`verify_sibling_api`).
- Verification: corpus-free quick-verify (`verify.bat` / `pytest`), full eval (`eval/eval_agenticrag.py`), CI on every push/PR.
- MIT `LICENSE`, `CONTRIBUTING.md`, this changelog, Quickstart README.

[0.1.0]: https://github.com/trentmilam/agentic-rag/releases/tag/v0.1.0
