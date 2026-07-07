# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Initial public release

First public release: cited, revision-aware retrieval over a real 321,124-chunk
corpus drawn from the IETF RFC ecosystem, with a deterministic supersession-graph
lookup and an MCP server.

### Added
- **Corpus fetch** (`corpus_fetch/`) — real HTTPS fetch of RFC full text, the
  `rfc-index.txt` supersession graph, community-submitted RFC errata, and 7 IANA
  protocol-parameter registries. Errata parsing has a floor-count sanity check that
  fails loudly if the source page's markup changes.
- **Ingest** (`ingest/`) — per-source-type connectors → chunk → embed
  (`BAAI/bge-base-en-v1.5`) → local Qdrant, with a real `is_current` currency flag
  derived from the obsoletion graph. Supports a from-scratch `--recreate` rebuild and
  a fast incremental path (see the README for the incremental path's known limits).
- **Registry** — a 5-module Consilium registry: `rfc_text` / `rfc_index` / `errata` /
  `iana_registry` retrieval modules (loaded straight from Qdrant, `current_only` by
  default) plus `SupersessionModule`, a deterministic, cycle-safe obsoletion-graph
  walk with a defensive node cap. `trust_tier` values are measured, not guessed.
- **Answer path** — routed and citation-gated through `consilium`; returns cited
  answers or an honest abstain, with no LLM in the answer path.
- **MCP server** (`agenticrag/mcp/server.py`) — FastMCP over stdio exposing `search`
  plus `get_obsoletion_chain` / `get_corrections` / `get_related` relationship tools
  (relationships via the `linkgraph` sibling, with a documented fallback envelope).
- **Guards** — an embedder-consistency check (`verify_embedder_marker`) and a sibling
  API-shape check (`verify_sibling_api`), both wired into `build_registry` so a
  mismatched embedder or a drifted `consilium` checkout fails loudly up front rather
  than silently producing meaningless scores or an opaque deep error.
- **Verification** — a corpus-free quick-verify (`verify.bat` / `scripts/verify.py` /
  `pytest`) covering the unit tests, MCP tool wrappers, and supersession cycle-safety;
  a corpus-dependent full eval (`eval/eval_agenticrag.py`); and GitHub Actions CI that
  reproduces the sibling layout and runs the quick-verify on every push/PR.
- MIT `LICENSE`, `CONTRIBUTING.md`, this changelog, and a Quickstart-first README.

[0.1.0]: https://github.com/trentmilam/agentic-rag/releases/tag/v0.1.0
