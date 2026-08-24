# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- **agentic-rag is standalone.** `consilium`, `RAGpack`, `linkgraph`, `activerag` and
  `chain-rag` were separate repositories that this one reached over `sys.path`; they are
  packages of this repository now, under `packages/`, brought across with `git subtree`
  so their own commit histories survive. `git clone && pip install -e . && pytest` works
  from a bare checkout — previously it stopped at `ModuleNotFoundError` during
  collection unless four sibling clones were laid out correctly beside it.
  - `agenticrag/_paths.py` is deleted along with 22 `add_sibling_paths()` calls across
    12 files and `bootstrap.verify_sibling_api()`, which existed only to detect a
    drifted sibling checkout.
  - The three separate sibling commit-pin lists (`requirements.txt`, `_paths.py`, the CI
    workflow) had drifted apart from one another and are all gone; there is nothing left
    to pin.
  - `conftest.py` and CI now both refuse to run if any merged package resolves to a
    namespace package or to a path outside this repository. Both failures are silent
    otherwise — the suite passes green against the wrong copy of the source.
  - `activerag.registry_bridge` no longer inserts a sibling `agentic-rag` checkout at the
    front of `sys.path` before importing from it, and `activerag.refresh_hook` no longer
    derives its data directory from the repository's own directory name.
  - `rag-reliability` remains a genuine external dependency, supplying `graphrx` and
    `headroom` to three of the merged packages. CI pins it and fails if the tests that
    use it report skipped rather than passing.
  - `pypdf` is declared in `requirements.txt`; RAGpack's extractor needs it, its test
    suite exercises it against real PDF bytes, and it had only ever been present
    incidentally. RAGpack's separate docTR/OCR CI job is preserved as its own job here.

- `ingest/run_ingest.py` now prints progress: a start line (files found / changed
  since last run), a heartbeat at most every 15s during the embed/upsert loop, and
  the existing final JSON summary, unchanged. Previously the whole run — minutes on
  a small corpus, hours on the full 321,124-chunk one — produced zero stdout, which
  a fresh-clone smoke test read as a hang.

## [0.1.1]

- Re-pin the linkgraph and RAGpack sibling checkouts (README quickstart,
  `requirements.txt`, CI) to currently-reachable commits. The previous pins were
  orphaned by a history rewrite in those repos, so a fresh clone's verbatim
  quickstart failed at `git checkout` — while CI stayed green, because
  `actions/checkout` fetches orphaned commits by exact SHA where a plain clone
  cannot. The pinned-to-tip diffs are docs/CI-only in both siblings.

## [0.1.0] — Initial public release

First public release: cited, revision-aware retrieval over a real 321,124-chunk
corpus drawn from the IETF RFC ecosystem, with a deterministic supersession-graph
lookup and an MCP server.

### Added
- **Corpus fetch** (`corpus_fetch/`) — HTTPS fetch of RFC full text, the `rfc-index.txt`
  supersession graph, RFC errata, and 7 IANA protocol-parameter registries.
- **Ingest** (`ingest/`) — per-source-type connectors → chunk → embed (`BAAI/bge-base-en-v1.5`)
  → local Qdrant, with an `is_current` flag derived from the obsoletion graph. From-scratch
  `--recreate` rebuild and a fast incremental path.
- **Registry** — 5-module Consilium registry: `rfc_text` / `rfc_index` / `errata` /
  `iana_registry` retrieval modules plus `SupersessionModule`, a deterministic, cycle-safe
  obsoletion-graph walk.
- **Answer path** — routed and citation-gated through `consilium`; cited answers or an honest
  abstain, no LLM in the answer path.
- **MCP server** (`agenticrag/mcp/server.py`) — FastMCP over stdio: `search` plus
  `get_obsoletion_chain` / `get_corrections` / `get_related`.
- **Guards** — embedder-consistency check (`verify_embedder_marker`) and a sibling API-shape
  check (`verify_sibling_api`), wired into `build_registry`.
- **Verification** — corpus-free quick-verify (`verify.bat` / `pytest`), a corpus-dependent full
  eval (`eval/eval_agenticrag.py`), and CI that runs the quick-verify on every push/PR.
- MIT `LICENSE`, `CONTRIBUTING.md`, this changelog, Quickstart README.

[0.1.0]: https://github.com/trentmilam/agentic-rag/releases/tag/v0.1.0
