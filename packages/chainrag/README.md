# chain-rag

A cited retrieval system over primary blockchain protocol documentation
(Bitcoin, Ethereum, Solana, Monero, Polygon, and Cardano), built on
[`packages/consilium`](../consilium)'s router/citation-gating spine and
[`packages/ragpack`](../ragpack)'s embedder/chunker/vector-store machinery. Ask a
real technical question about any of the six chains (or one that spans two of
them) and get back an answer built entirely out of real cited chunks from the
source documents, or an honest abstain. There is no LLM anywhere in the answer
path: retrieval, a deterministic router, and a citation-integrity gate, nothing
else, so every line of every answer traces to an actual document.

It is a second, independent vertical on the same architecture: its own Consilium
`Registry`/`Router` instance for a standalone domain, zero coupling to any other
vertical, sharing only the generic library underneath.

## This package is not standalone

`chainrag` is `packages/chainrag` in the `agentic-rag` monorepo. `consilium` and
`ragpack` are packages of the same repository: once the repo root's
`pip install -e .` has run, `import consilium` and `import ragpack` resolve
with no cloning and no `sys.path` insertion.

One dependency is genuinely still outside this repo:
[rag-reliability](https://github.com/trentmilam/rag-reliability), which supplies
four of its gate tools (VecStamp, ChunkLedger, Plumbline, Legigate). It is
public now; clone it next to the agentic-rag repo itself (a sibling directory,
not nested inside it) to run `scripts/run_reliability_gates.py`. The chat UI,
the ingest pipeline, and the eval all run without it; only that one script
needs it.

```
git clone https://github.com/trentmilam/rag-reliability
```

Neither `rag-reliability`'s tools nor `chainrag` itself are pip-installed or
vendored the way `consilium`/`ragpack` are: `rag-reliability` is imported by
putting each individual tool subdir (it has no `__init__.py`) on `sys.path`.
See `chainrag/_paths.py::add_sibling_paths()`, called by every entry file
before importing anything from that sibling repo.

Move this repo without `consilium` installed and every import fails
immediately and loudly; there is no silent degraded mode.

## Running it

```
cd packages/chainrag
app.bat     # chat UI (gr.ChatInterface), own venv, no browser auto-launch
demo.bat    # scripted 8-question transcript, no typing required
```

Both `app.bat` and `demo.bat` hardcode `%~dp0.venv\Scripts\python.exe`, so
create that venv first: `python -m venv .venv`, then install from
`requirements.txt` (it pins a CUDA-tagged `torch` build; see the comment at
the top of that file for the matching `--index-url`).

Both are fully offline at query time beyond a local Qdrant read and local
embedding: no live network calls, no LLM.

## Running the eval

```
cd packages/chainrag
.venv/Scripts/python.exe eval/eval_chainrag.py
```

Deterministic given the already-ingested corpus (22 documents, ~1,055 chunks
across all 6 chains; see `sources.yaml`). Uses the real embedder
(`BAAI/bge-base-en-v1.5`), the exact one that ingested the corpus, so this
proves genuine semantic retrieval end-to-end, not wiring alone. Eight checks:

- one held-out, naturally-phrased technical question **per chain** (6): asserts
  the expected chain contributed a citation and the router didn't abstain;
- one genuine **cross-chain comparison** (Bitcoin PoW vs. Cardano's Ouroboros
  PoS): asserts both expected chains contributed citations;
- one **out-of-scope** question ("How do you properly season a cast iron
  skillet?"): asserts an honest abstain.

## Real dense embedders need per-corpus calibration

Consilium's `Router` ships library defaults (`floor=0.11`, `anchor_centroid=0.25`,
`anchor_best_chunk=0.25`) that assume a near-zero baseline cosine similarity
between unrelated text: true for a crude bag-of-words `HashEmbedder`, **false**
for a real dense sentence embedder. Measured directly against this corpus: every
genuine in-scope query's anchor module has descriptor-centroid cosine >=0.626 and
>=2 subject-keyword hits, while 10 diverse out-of-scope probes (recipes, weather,
gibberish) never exceeded centroid 0.492 and always had 0 keyword hits. But
best-chunk cosine (a max over ~1,055 chunks) is a saturated order statistic that
cleared the 0.25 anchor threshold for *every* probe, including gibberish. Left at
the library defaults, the out-of-scope check reliably failed and the answer to
every query, on-topic or not, cited all six chains indiscriminately.

`chainrag/bootstrap.py::ROUTER_KWARGS` recalibrates `floor`/`anchor_centroid`/
`anchor_best_chunk` for this embedder+corpus pair specifically, using Consilium's
own documented per-instance constructor kwargs. Consilium's shared source and its
library-wide defaults (which every other Consilium instance still uses) are
untouched. This is the kind of gap the reliability-gate suite below is built to
surface rather than paper over.

## Reliability gates

```
.venv/Scripts/python.exe scripts/run_reliability_gates.py
```

Four gates from `rag-reliability`, run against the real ingested corpus:

- `VecStamp` checks embedding build/load identity: the query-time embedder is
  bit-identical to the one that ingested the corpus.
- `ChunkLedger` checks reference-free conservation, that no document or chunk
  silently dropped structural content (headings, tables, code blocks, links)
  during ingest.
- `Plumbline` checks that every citation resolves back to a real span in its
  source document (fuzzy match survives whitespace/OCR noise, not genuine
  corruption).
- `Legigate` is the OCR legibility gate. It correctly reports N/A here, since
  the real corpus needed zero OCR (all 22 sources are born-digital).

Current reference run: **3 PASS, 0 FAIL, 1 N/A**.

## Layout

```
chainrag/
  _paths.py         sibling-path bootstrap (rag-reliability only)
  bootstrap.py      build_registry(embedder) -> consilium.registry.Registry,
                     the 6 chain Descriptors, ROUTER_KWARGS (see calibration note above)
  qdrant_loader.py  loads a consilium Module's chunks straight from Qdrant
ingest/
  sources.py        SourceDoc manifest schema + loader/validator
  chunk.py          header/section-aware pre-splitter (wraps RAGpack's chunk_text)
  ocr.py            EasyOCR primary / PaddleOCR fallback, confidence-gated
  embed_config.py   single shared Settings (model/qdrant path) for ingest + query time
  run_ingest.py     manifest -> extract/clean/OCR -> chunk -> embed -> Qdrant
eval/
  smoke_eval.py     wiring smoke test (hash + real embedder stages)
  eval_chainrag.py  the 8-check production eval described above
scripts/
  run_reliability_gates.py   VecStamp/ChunkLedger/Plumbline/Legigate over the real corpus
sources.yaml        the 22-document production manifest (chain, source_url, license_note)
app.py               gr.ChatInterface chat UI
run_demo.py          scripted 8-question narrated transcript
```
