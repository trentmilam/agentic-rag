# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
