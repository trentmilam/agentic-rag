# agentic-rag

[![CI](https://github.com/trentmilam/agentic-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/trentmilam/agentic-rag/actions/workflows/ci.yml)

Cited, revision-aware retrieval over the IETF RFC corpus (~321k chunks).

- Sources: RFC full text, RFC index supersession graph, RFC errata, IANA registries
- Ingest via [`ragpack`](packages/ragpack), routed and citation-gated by [`consilium`](packages/consilium)
- Answers are cited chunks or an abstain
- Obsoletion questions ("what replaced RFC 2616?") are answered by `SupersessionModule`, a deterministic graph lookup
- No LLM in the answer path

## Quickstart

```bat
git clone https://github.com/trentmilam/agentic-rag
cd agentic-rag
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python scripts\verify.py
```

Answering a real question needs the ingested corpus. See [The corpus](#the-corpus) and [Verify](#verify).

## One repo, five merged tools

Each tool keeps its own tree and commit history under `packages/<name>/`.

| package | what it is | tests |
|---|---|---|
| [`packages/consilium`](packages/consilium) | the routing / citation-gating spine: Registry, Router, compose, integrity gate, ComputeModule | 5 eval suites |
| [`packages/ragpack`](packages/ragpack) | ingest, chunking, embedding, the Qdrant store wrapper | 31 |
| [`packages/linkgraph`](packages/linkgraph) | the cross-document relationship graph behind the MCP relationship tools | 50 |
| [`packages/activerag`](packages/activerag) | evidence-thinness detection and bounded hunt-and-retry | 54 |
| [`packages/chainrag`](packages/chainrag) | a second vertical over blockchain protocol docs | -- |

- CI asserts every package resolves to a file inside this repo
- `rag-reliability` is the one outside dependency: `graphrx`, `headroom`, `vecstamp`, `chunkledger`, `plumbline`, `legigate`
- Resolved by path today; packaging it is open
- CI checks it out pinned and fails if those integration tests skip

## The corpus

| source type | what it is | real chunks | current (non-obsoleted) |
|---|---|---:|---:|
| `rfc_text` | verbatim RFC full text | 306,939 | 225,809 |
| `rfc_index` | per-RFC index card (title/authors/date/status/obsoletes/updates) | 5,854 | 4,663 |
| `errata` | real community-submitted RFC corrections | 7,295 | 7,295 (n/a: no revision concept) |
| `iana_registry` | 7 real IANA protocol-parameter registries, rendered as markdown tables | 1,036 | 1,036 (n/a: no revision concept) |

- 321,124 chunks total, embedded with `BAAI/bge-base-en-v1.5`
- `is_current` applies to `rfc_text` and `rfc_index` only (see [the revision guard](#the-revision-guard-proven))
- `data/` is gitignored; the corpus is fetched from rfc-editor.org and iana.org

## Five modules, one router

`agenticrag/bootstrap.py::build_registry` assembles a 5-module consilium `Registry`.

- 4 retrieval modules, loaded from Qdrant with `current_only=True` (`agenticrag/registry_loader.py`)
- `SupersessionModule` (`agenticrag/supersession.py`): graph walk over `data/entities/revisions.json` (9,794 RFCs), cycle-safe, capped at 50 visited nodes
- `verify_embedder_marker` runs first and fails if the configured embedder differs from the one that ingested the store

`errata` trust tier is 0.55, against 0.9-0.95 for `rfc_text`, `rfc_index` and `iana_registry`. Of 5,061 errata records:

- 2,400 (47.4%) Verified
- 1,781 (35.2%) Held for Document Update
- 679 (13.4%) Rejected
- 201 (4.0%) Reported

## MCP server

`agenticrag/mcp/server.py`: [Model Context Protocol](https://modelcontextprotocol.io) server over stdio (`mcp>=1.28.1`, FastMCP). Four tools:

- `search(query)`: cited/abstain answer path (`consilium.compute.answer_v3`), passed through verbatim
- `get_obsoletion_chain(rfc_id)`, `get_corrections(rfc_id)`, `get_related(entity_id)`: relationship graph via `linkgraph` (`agenticrag/relationships.py`); each returns `{"ok": false, "fallback": ...}` if `linkgraph` is absent

```bat
.venv\Scripts\python -m agenticrag.mcp.server
```

Tool logic has no `mcp` or Qdrant dependency (`agenticrag/mcp/test_server.py`).

## Verify

Quick verify (corpus-free):

```bat
verify.bat        :: or:  .venv\Scripts\python -m pytest -q
```

- Runs agentic-rag's MCP wrapper and supersession cycle-safety tests, plus the pytest suites of `consilium`, `ragpack`, `linkgraph`, `activerag`
- `chainrag` has no pytest suite; its eval runs separately
- CI runs this on every push

Full verify (needs the ingested corpus):

```bat
.venv\Scripts\python eval\eval_agenticrag.py
```

- Deterministic, no re-ingestion, real embedder
- ~3.3 min (measured, 196s): ~60s registry build, then ~12s per router/answer pass
- Qdrant local mode: exact brute-force search, no ANN index
- Checks:
  - one in-scope query per source type (module + >=1 citation)
  - RFC 2616 obsoletion: successor set exactly `{7230, 7231, 7232, 7233, 7234, 7235}`
  - one out-of-scope query: abstain
  - revision-guard structural exclusion
  - RFC 791 resolves `current`
  - RFC 99999 resolves `not_found`

`eval/prove_revision_guard.py`: standalone narrated revision-guard proof.
`eval/smoke_ingest_real.py`: fetch, ingest and Qdrant wiring with `HashEmbedder` (needs `corpus_fetch.fetch_all` run first; no GPU).

<a name="the-revision-guard-proven"></a>
## The revision guard, proven

RFC 2616 (HTTP/1.1) was entirely superseded by six documents (RFC 7230-7235).

1. Structural exclusion: its `rfc_text` chunks exist in Qdrant (`current_only=False` shows them) and are absent from the default `current_only=True` module, because `data/entities/revisions.json["RFC2616"]["obsoleted_by"]` is non-empty.
2. Correct path: `SupersessionModule` returns the 6-way successor list (RFC 7230-7235).

## Router calibration

`consilium.router.Router` defaults: `floor=0.11`, `anchor_centroid=0.25`, `anchor_best_chunk=0.25`. `agenticrag/calibrate.py` measures scores against the real corpus and embedder. Per-instance kwargs: `agenticrag/bootstrap.py::ROUTER_KWARGS`.

```bat
.venv\Scripts\python agenticrag\calibrate.py
```

## GPU note (ingest only)

- GPU is used for ingest (`ingest/run_ingest.py`, `onnxruntime`); queries run on CPU
- `onnxruntime-gpu` without matching CUDA runtime DLLs prints a red `CUDAExecutionProvider` / `cublasLt64_*.dll` error and falls back to CPU
- Warning is harmless; appears on ingest and query runs
- CPU ingest: ~6 chunks/sec measured, ≈14.9 hours computed for 321,124 chunks
- RTX 5090: ~650 chunks/sec measured, ≈8 minutes

Optional CUDA runtime wheels (match onnxruntime-gpu 1.27.0 / CUDA 13 in `requirements.txt`):

```bat
.venv\Scripts\python -m pip install nvidia-cublas nvidia-cuda-runtime nvidia-cufft nvidia-cudnn-cu13
```

Or put a CUDA-enabled PyTorch `torch/lib` directory on `PATH`.

## Ingest re-runs (known limitation)

`ingest/run_ingest.py`: `--recreate` for a full rebuild, incremental path otherwise (re-embeds files whose content hash changed).

- Incremental: `is_current` can go stale if an RFC is newly obsoleted in a later `rfc-index.txt` and its own text file is unchanged
- Incremental: orphaned Qdrant points are not deleted when a document re-ingests to fewer chunks
- Use `--recreate` for a consistent store

## Layout

```
agenticrag/
  embed_config.py     shared Settings (model/qdrant path) + embedder-consistency guard
  registry_loader.py  loads a consilium Module's chunks straight from Qdrant (current_only guard)
  bootstrap.py        build_registry(embedder, client=None) -> Registry; the 5 Descriptors; ROUTER_KWARGS
  supersession.py     SupersessionModule: real Obsoletes/Obsoleted-by graph walk, cycle-safe
  relationships.py    thin bridge into linkgraph (get_related / _obsoletion_chain / _corrections)
  calibrate.py        real router-score measurement script
  mcp/
    server.py         FastMCP server: search + the 3 relationship tools (stdio)
    test_server.py    fixture-only tests for the tool logic (no mcp package, no Qdrant)
corpus_fetch/         real HTTPS fetch of RFC full text / rfc-index.txt / errata / IANA registries
ingest/
  connectors/         per-source-type extract() -> ExtractedDoc (+ the revisions-index builder)
  run_ingest.py       raw files -> chunk -> embed -> Qdrant, real is_current currency check
eval/
  smoke_ingest_real.py               corpus_fetch -> ingest -> Qdrant wiring smoke (HashEmbedder)
  eval_agenticrag.py                 production eval (full verify; needs the ingested corpus)
  prove_revision_guard.py            standalone, narrated revision-guard proof
  test_supersession_cycle_safety.py  cycle-safety unit tests (synthetic graph; corpus-free)
tests/                unit tests for connectors / registry_loader / bootstrap (corpus-free)
packages/             the five merged tools, each keeping its own tree and history
  consilium/          routing / citation-gating spine (+ its 5 eval suites)
  ragpack/            ingest / chunk / embed / Qdrant store (src-layout)
  linkgraph/          cross-document relationship graph
  activerag/          evidence-thinness detection and bounded hunt-and-retry
  chainrag/           the blockchain-docs vertical
app.py                gr.ChatInterface chat UI
run_demo.py           scripted 3-question narrated transcript
```

## License

Code: [MIT](LICENSE) (c) 2026 Trent Milam.

Corpus is not included. It is fetched locally from rfc-editor.org and iana.org. IETF RFC/errata text is subject to the [IETF Trust Legal Provisions](https://trustee.ietf.org/documents/trust-legal-provisions/); each fetched document keeps its own copyright notice. IANA registry data is published by IANA. This project redistributes none of it.
