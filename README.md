# agentic-rag

[![CI](https://github.com/trentmilam/agentic-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/trentmilam/agentic-rag/actions/workflows/ci.yml)

Cited, revision-aware retrieval over a **real** corpus drawn from the IETF RFC
ecosystem -- RFC full text, the RFC index's real Obsoletes/Obsoleted-by/Updates
supersession graph, real community-submitted RFC errata, and real IANA
protocol-parameter registries -- fetched over HTTPS (`corpus_fetch/`) and
ingested through [RAGpack](https://github.com/trentmilam/RAGpack) into a
searchable vector store (321,124 real chunks), then routed and citation-gated
through the [consilium](https://github.com/trentmilam/consilium) spine.

Ask a real question about an IETF protocol spec, an RFC's authorship/status, a
real errata correction, or an IANA registry entry, and get back an answer built
entirely out of **real cited chunks -- or an honest abstain**. The one exception
is an obsoletion question ("what replaced RFC 2616?"): there is no "current
revision" of RFC 2616's own text to retrieve (it was entirely superseded by six
later documents, RFC 7230-7235 -- IETF's own famous multi-way obsoletion case),
so that is answered by `SupersessionModule`, a deterministic graph lookup over
the real Obsoletes/Obsoleted-by graph, not retrieval. **No LLM anywhere in the
answer path.**

## Quickstart

This repo is **not standalone** -- it imports two sibling capability repos (see
[Honest scope](#honest-scope) below). Clone all of them side-by-side under one
parent directory, then build the corpus once:

```bat
:: 1. Clone this repo + its siblings side-by-side (one shared parent dir):
::      <parent>/{agentic-rag, consilium, linkgraph, RAGpack}
:: Check each sibling out at the exact commit this release was verified against
:: (same SHAs CI pins and requirements.txt records) so the human path and the CI
:: path are provably identical -- newer sibling tips may have drifted.
git clone https://github.com/trentmilam/agentic-rag
git clone https://github.com/trentmilam/consilium && git -C consilium checkout 5228cbb
git clone https://github.com/trentmilam/linkgraph && git -C linkgraph checkout 46bdd04
git clone https://github.com/trentmilam/RAGpack   && git -C RAGpack   checkout a0078fb

:: 2. Create agentic-rag's venv (Python 3.12) + install its deps + RAGpack (editable):
cd agentic-rag
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e ..\RAGpack

:: 3. Fetch the real corpus over HTTPS (rfc-editor.org / iana.org). Downloads a few
::    hundred MB of text; takes a while on a home connection. Writes to data/raw/.
.venv\Scripts\python -m corpus_fetch.fetch_all

:: 4. Ingest -> chunk -> embed -> Qdrant. The heavy step: ~321k chunks embedded with
::    BAAI/bge-base-en-v1.5. Minutes on a GPU, many hours on CPU (see "GPU note").
::    Produces a multi-GB local Qdrant store under data/qdrant/ (both gitignored).
.venv\Scripts\python ingest\run_ingest.py

:: 5. See it run. Two costs, both on CPU and both disclosed as they happen:
::    - registry build does a one-time ~60s scan of the corpus for the small
::      poison-quarantine set (measured, first launch), with per-module progress;
::    - then each distinct query takes ~12s (measured), running routing + retrieval
::      as native Qdrant vector searches instead of a pure-Python scan -- the
::      demo/app print a live "working..." heartbeat so this never reads as a hang.
demo.bat      :: scripted 3-question transcript, no typing
app.bat       :: interactive chat UI (gradio, no browser auto-launch)
```

POSIX note: every launcher ships in both forms -- `demo.bat`/`app.bat`/`verify.bat`
on Windows and `demo.sh`/`app.sh`/`verify.sh` on macOS/Linux (thin wrappers around
the same `python` commands, using `.venv/bin/python`). Nothing is Windows-only
underneath.

Nothing ships pre-built: `data/` (raw corpus, Qdrant store, entity index) is
entirely gitignored, so steps 3-4 are required before any query command works.
Skipping them and running the demo raises a clear "collection does not exist --
build it first" error, not a raw driver stack trace.

**Try it fast (small subset).** The full corpus is large (step 4 is the long
pole). To sanity-check the whole fetch → ingest → query pipeline in minutes
instead of committing to the full build, cap the corpus to the first few hundred
RFCs: `python -m corpus_fetch.fetch_all --max-rfc-number 300`, then the same
`python ingest/run_ingest.py`. Everything downstream (registry, router, demo, MCP
server) works identically on the subset -- there's just less of it.

<a name="honest-scope"></a>
## Honest scope: the sibling dependencies

`agentic-rag` reuses two sibling repos as libraries, each a separate git repo
living next to this one under the same parent directory, neither pip-installed --
each imported by putting its root on `sys.path` (`agenticrag/_paths.py`):

| sibling | required by | how |
|---|---|---|
| **consilium** | every entrypoint -- `app.py`, `run_demo.py`, the eval, the MCP server | `sys.path` (the routing / citation-gating spine: Registry, Router, compose, integrity gate, ComputeModule) |
| **linkgraph** | the MCP server's relationship tools only (`agenticrag/relationships.py`) -- the chat UI, demo, and eval never import it | `sys.path` |
| **RAGpack** | ingest + embedding + the Qdrant store wrapper | pip-installed **editable** into this repo's venv (`pip install -e ../RAGpack`) -- `import ragpack` needs no `sys.path` entry |

Move this repo without `consilium` and every entrypoint fails immediately and
loudly at import -- there is no silent degraded mode. `linkgraph`'s absence
degrades only the MCP relationship tools (they return a documented
`{"ok": false, "fallback": ...}` envelope), never the core answer path.

Verified this release against `consilium@5228cbb`, `linkgraph@46bdd04`,
`RAGpack@a0078fb` (see `requirements.txt`).

## The corpus

| source type | what it is | real chunks | current (non-obsoleted) |
|---|---|---:|---:|
| `rfc_text` | verbatim RFC full text | 306,939 | 225,809 |
| `rfc_index` | per-RFC index card (title/authors/date/status/obsoletes/updates) | 5,854 | 4,663 |
| `errata` | real community-submitted RFC corrections | 7,295 | 7,295 (n/a -- no revision concept) |
| `iana_registry` | 7 real IANA protocol-parameter registries, rendered as markdown tables | 1,036 | 1,036 (n/a -- no revision concept) |

321,124 total real chunks, embedded with the real `BAAI/bge-base-en-v1.5`
model. `rfc_text`/`rfc_index` are the only source types with a revision
concept -- `is_current` there is a real structural fact (see [the revision
guard](#the-revision-guard-proven)), not guessed.

## Five modules, one router

`agenticrag/bootstrap.py::build_registry` assembles a real 5-module consilium
`Registry`: the 4 retrieval modules above (each loaded straight from Qdrant,
`current_only=True` by default -- see `agenticrag/registry_loader.py`), plus
`SupersessionModule` (`agenticrag/supersession.py`), a `ComputeModule` that
parses `data/entities/revisions.json` -- the real Obsoletes/Obsoleted-by graph
for all 9,794 RFCs in the live index -- once at construction and answers
obsoletion questions with a deterministic, cycle-safe graph walk (bounded at 50
visited nodes -- a defensive cap, not an expected real limit; real IETF
obsoletion components are small).

`build_registry` also fails loud if the process's configured embedder does not
match the one that ingested the store (`verify_embedder_marker`, called first) --
otherwise cosine scores would be silently meaningless -- and closes any Qdrant
client it opened itself once the modules are loaded (retrieval is fully
in-memory afterward), so it does not hold the local-mode store's lock for the
caller's whole process lifetime.

`errata`'s `trust_tier` (0.55, well below `rfc_text`/`rfc_index`/`iana_registry`'s
0.9-0.95) is measured, not guessed: of 5,061 real errata records ingested,
**only 2,400 (47.4%) are `Verified`** by the RFC Editor -- 1,781 (35.2%) are
`Held for Document Update`, 679 (13.4%) are outright `Rejected`, and 201 (4.0%)
are still `Reported`. Fewer than half of real submitted corrections are
RFC-Editor-confirmed, so this module corrects the primary text without being
uniformly authoritative itself.

## MCP server

`agenticrag/mcp/server.py` exposes the answer path as a
[Model Context Protocol](https://modelcontextprotocol.io) server over stdio
(`mcp>=1.28.1`, FastMCP). Four tools:

- `search(query)` -- the full cited/abstain answer path (`consilium.compute.answer_v3`), passed through verbatim (an honest abstain stays an abstain);
- `get_obsoletion_chain(rfc_id)` / `get_corrections(rfc_id)` / `get_related(entity_id)` -- the relationship graph, via the `linkgraph` sibling (`agenticrag/relationships.py`); each returns a documented `{"ok": false, "fallback": ...}` envelope if that sibling is absent.

Run it: `.venv\Scripts\python -m agenticrag.mcp.server` (stdio transport -- an
MCP client launches it and speaks the protocol over stdin/stdout). The tool
*logic* is import-light and has no `mcp`/Qdrant dependency, so it unit-tests
without either (`agenticrag/mcp/test_server.py`).

## Verify

**Quick verify** (fast, corpus-free -- no ingested corpus needed):

```bat
verify.bat        :: or:  .venv\Scripts\python -m pytest -q
```

Runs the MCP tool-wrapper tests and the supersession graph-walk cycle-safety
suite. This is what CI runs on every push (see the badge above).

**Full verify** (needs the ingested 321k-chunk corpus from the Quickstart):

```bat
.venv\Scripts\python eval\eval_agenticrag.py
```

Deterministic given the already-ingested corpus; no re-ingestion. Uses the real
embedder -- the exact one that ingested the corpus -- so this proves genuine
semantic retrieval end-to-end, not wiring alone. Takes ~3.3 min on this
hardware (measured, full run: 196s): a one-time ~60s registry build (a single
scan of the corpus for the small poison-quarantine set -- not a load of all 321k
vectors), then the router/answer passes at ~12s each. Each pass runs routing and
retrieval as native Qdrant vector searches; Qdrant's embedded local mode is exact
brute-force (no ANN index), so a search still scans the filtered subset -- but in
native code, materializing only the top-k, ~16x faster than the old pure-Python
per-chunk scan. (Sub-second search would need Qdrant server mode's HNSW index;
local mode keeps the repo self-contained -- no server to run.) It
checks: one in-scope
query per source type (sensible module + >=1 real citation); the RFC 2616
obsoletion query (successor set is **exactly** `{7230, 7231, 7232, 7233, 7234,
7235}`); one out-of-scope query (honest abstain); the revision-guard structural
exclusion (below); a genuinely current RFC (791) resolving `current`; and an
absent RFC number (99999) resolving `not_found`, not a crash.

`eval/prove_revision_guard.py` is the same structural proof as a standalone,
narrated script. `eval/smoke_ingest_real.py` proves the fetch->ingest->Qdrant
wiring with the zero-cost `HashEmbedder` (needs `corpus_fetch.fetch_all` to have
run, but no GPU/embedding model).

<a name="the-revision-guard-proven"></a>
## The revision guard, proven

RFC 2616 (HTTP/1.1) is a real, single, whole document -- there is no "current
revision" of it; it was entirely superseded by six different documents. The
guard property here is two real, checkable facts, not one "corrected value":

1. **Structural exclusion.** RFC 2616's own `rfc_text` chunks exist in Qdrant
   (loading the `rfc_text` module a second time with `current_only=False`
   proves they're there) but are absent from the default `current_only=True`
   module every query actually uses -- because
   `data/entities/revisions.json["RFC2616"]["obsoleted_by"]` is real and
   non-empty. The data exists; it's structurally filtered, not accidentally
   missing.
2. **The correct path to the answer.** `SupersessionModule` is the explicit way
   to learn what happened to RFC 2616 -- a query naming it returns the real
   6-way successor list (RFC 7230-7235).

## Router calibration -- measured, not guessed

`consilium.router.Router`'s stated library defaults (`floor=0.11`,
`anchor_centroid=0.25`, `anchor_best_chunk=0.25`) assume a near-zero baseline
cosine between unrelated text -- true for a bag-of-words `HashEmbedder`, not
necessarily true for a real dense embedder over a 321k-chunk corpus (the same
gap shows up even at a much smaller ~1,100-chunk scale). `agenticrag/calibrate.py`
measures this directly against the real corpus + real embedder rather than
assuming it; see `agenticrag/bootstrap.py::ROUTER_KWARGS` for the resulting
per-instance kwargs and the real numbers that justified the decision.

```bat
.venv\Scripts\python agenticrag\calibrate.py
```

## GPU note (ingest only)

GPU matters for exactly one step: the corpus **ingest** (`ingest/run_ingest.py`),
which embeds ~321k chunks with `BAAI/bge-base-en-v1.5` via `onnxruntime`. At
**query time** you only embed the (short) query string, so the launchers run fine
on CPU with no GPU setup -- which is why they no longer touch any GPU config.

Expected-and-harmless warning: if `onnxruntime-gpu` is installed but its matching
CUDA runtime DLLs aren't on the search path, you'll see an alarming red
`CUDAExecutionProvider` / `Error loading ... cublasLt64_*.dll ... missing` block --
**on any run, ingest or query**, not just ingest. It is not a failure: onnxruntime
falls back to CPU and continues (for a query the embed is one short string, so the
CPU fallback is instant). Ignore it, or install the DLLs below to silence it.

For a fast ingest, `onnxruntime-gpu`'s CUDA execution provider needs those CUDA
runtime DLLs on the DLL search path. `pip install onnxruntime-gpu` alone does
**not** bundle them, and without them onnxruntime falls back to CPU (measured:
~6 chunks/sec -- computed: ≈14.9 hours for the full 321,124-chunk corpus) rather
than raising. To get real GPU execution (measured: ~650 chunks/sec on an RTX 5090,
i.e. ≈8 minutes for the full corpus), install the matching CUDA runtime wheels
into this repo's own venv, e.g.:

```bat
.venv\Scripts\python -m pip install nvidia-cublas-cu13 nvidia-cudnn-cu13
```

(match the `-cuNN` suffix to your `onnxruntime-gpu` build's CUDA major version),
or put any CUDA-enabled PyTorch install's `torch/lib` directory on `PATH` before
running the ingest. Either way this is an **optional acceleration of the one-time
ingest**, never required to run the demo or serve queries.

## Ingest re-runs (known limitation)

`ingest/run_ingest.py` supports a from-scratch `--recreate` rebuild and a fast
incremental path (only re-embeds raw files whose content hash changed). The
incremental path has two known limitations, deliberately not papered over: (1) it
keys "changed" purely on each raw file's byte hash, so if an RFC becomes newly
obsoleted in a later `rfc-index.txt` refresh *without its own text file
changing*, its `is_current` flag can go stale; and (2) it does not delete
orphaned Qdrant points for a document that re-ingests to fewer chunks. For a
guaranteed-consistent store, run `ingest/run_ingest.py --recreate` (a full
rebuild). Closing both limitations in the incremental path is future work.

## Layout

```
agenticrag/
  _paths.py           sibling-path bootstrap (consilium, linkgraph)
  embed_config.py     shared Settings (model/qdrant path) + embedder-consistency guard
  registry_loader.py  loads a consilium Module's chunks straight from Qdrant (current_only guard)
  bootstrap.py        build_registry(embedder, client=None) -> Registry; the 5 Descriptors; ROUTER_KWARGS
  supersession.py     SupersessionModule -- real Obsoletes/Obsoleted-by graph walk, cycle-safe
  relationships.py    thin bridge into the linkgraph sibling (get_related / _obsoletion_chain / _corrections)
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
app.py                gr.ChatInterface chat UI
run_demo.py           scripted 3-question narrated transcript
```

## License

Code: [MIT](LICENSE) (c) 2026 Trent Milam.

The corpus is **not** included in this repo (`data/` is gitignored); it is
fetched at build time from rfc-editor.org and iana.org. IETF RFC/errata text is
subject to the [IETF Trust Legal Provisions](https://trustee.ietf.org/documents/trust-legal-provisions/)
(the fetch preserves each document's own copyright/Trust notice intact); IANA
registry data is published by IANA. This project redistributes none of it -- it
fetches it, locally, on your machine.
