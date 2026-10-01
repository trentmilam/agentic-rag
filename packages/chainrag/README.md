# chain-rag

Cited retrieval over primary blockchain protocol documentation: Bitcoin, Ethereum, Solana, Monero, Polygon, Cardano.

- Built on [`packages/consilium`](../consilium) (router, citation gating) and [`packages/ragpack`](../ragpack) (embedder, chunker, vector store).
- Answers are cited chunks or an abstain.
- No LLM in the answer path: retrieval, deterministic router, citation-integrity gate.
- Own Consilium `Registry`/`Router` instance.

## Dependencies

After the repo root `pip install -e .`, `import consilium` and `import ragpack` resolve.

External: [rag-reliability](https://github.com/trentmilam/rag-reliability), for four gate tools (VecStamp, ChunkLedger, Plumbline, Legigate). Only `scripts/run_reliability_gates.py` needs it.

```
git clone https://github.com/trentmilam/rag-reliability
```

- Clone it as a sibling of the agentic-rag repo.
- Each tool subdir is put on `sys.path` (`chainrag/_paths.py::add_sibling_paths()`). It has no `__init__.py`.
- Without `consilium` installed, every import fails.

## Running it

```
cd packages/chainrag
app.bat     # chat UI (gr.ChatInterface), own venv, no browser auto-launch
demo.bat    # scripted 8-question transcript
```

- Both use `%~dp0.venv\Scripts\python.exe`. Create it with `python -m venv .venv`, then install `requirements.txt` (pins a CUDA-tagged `torch`; see the file header for `--index-url`).
- Offline at query time apart from a local Qdrant read and local embedding.

## Eval

```
cd packages/chainrag
.venv/Scripts/python.exe eval/eval_chainrag.py
```

- 22 documents, ~1,055 chunks, 6 chains (`sources.yaml`).
- Deterministic given the ingested corpus.
- Embedder: `BAAI/bge-base-en-v1.5`, same as ingest.
- 8 checks:
  - 6 held-out technical questions, one per chain: expected chain cited, no abstain.
  - 1 cross-chain comparison (Bitcoin PoW vs Cardano Ouroboros PoS): both chains cited.
  - 1 out-of-scope question (cast iron skillet): abstain.

## Router calibration

Consilium library defaults (`floor=0.11`, `anchor_centroid=0.25`, `anchor_best_chunk=0.25`) were set for `HashEmbedder`. A dense sentence embedder has higher baseline cosine similarity.

Measured on this corpus:

- In-scope queries: descriptor-centroid cosine >=0.626, >=2 subject-keyword hits.
- 10 out-of-scope probes: centroid never above 0.492, 0 keyword hits.
- Best-chunk cosine cleared 0.25 for every probe, gibberish included.
- At library defaults, the out-of-scope check failed and every query cited all six chains.

`chainrag/bootstrap.py::ROUTER_KWARGS` sets `floor`, `anchor_centroid` and `anchor_best_chunk` for this embedder and corpus. Consilium's shared source and defaults are unchanged.

## Reliability gates

```
.venv/Scripts/python.exe scripts/run_reliability_gates.py
```

Run against the ingested corpus.

- `VecStamp`: query-time embedder matches the ingest embedder.
- `ChunkLedger`: no document or chunk dropped structural content (headings, tables, code blocks, links) during ingest.
- `Plumbline`: every citation resolves to a real span in its source.
- `Legigate`: OCR legibility. N/A here, all 22 sources are born-digital.

Reference run: 3 PASS, 0 FAIL, 1 N/A.

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
