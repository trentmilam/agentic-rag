# RAGpack

**Mill your documents into a searchable vector store — GPU-optional embeddings, optional GPU OCR, Qdrant-backed.**

![ci](https://github.com/trentmilam/RAGpack/actions/workflows/ci.yml/badge.svg)

`RAGpack` turns a folder of documents — Markdown, code, text, and PDFs — into a semantic search
index in one line. It extracts text (with optional **GPU OCR** for scanned PDFs), chunks it with
overlap, embeds it on **CPU or CUDA**, and stores it in **Qdrant** — embedded on disk with zero
setup, or a real server when you scale.

```python
from ragpack import RAGpack, Settings

mill = RAGpack(Settings(qdrant="./data", device="auto"))   # CUDA if available, else CPU
mill.ingest("./docs")
for hit in mill.search("how does the retry logic work?"):
    print(f"{hit.score:.3f}  {hit.source}\n{hit.text[:200]}\n")
```

…or from the shell:

```bash
ragpack ingest ./docs  --qdrant ./data
ragpack search "how does the retry logic work?" --qdrant ./data
```

## Install

Not yet on PyPI (the name `ragpack` there is an unrelated project), so install from source:

```bash
git clone https://github.com/trentmilam/RAGpack
cd RAGpack
pip install -e .             # CPU
pip install -e ".[gpu]"     # CUDA embeddings (fastembed-gpu + onnxruntime-gpu)
pip install -e ".[ocr]"     # + GPU OCR for scanned PDFs (docTR, uses CUDA when a CUDA PyTorch build is present)
```

## CPU or GPU — one switch

`device="auto"` (the default) uses CUDA when ONNX Runtime exposes a `CUDAExecutionProvider`, and
falls back to CPU otherwise. `device="cuda"` is **fail-closed**: it raises rather than silently
dropping to CPU, so a GPU run is always actually a GPU run. Set it in code, per-CLI-call (`--device`),
or via `RAGPACK_DEVICE`.

## What you get

- **Extraction** — text/code/markdown, text-layer PDFs (`pypdf`), and, with `[ocr]`, scanned or
  image-only PDFs via docTR (GPU-accelerated automatically when a CUDA PyTorch build is present).
  `ocr="auto"` only OCRs when the text layer is empty or garbled.
- **Chunking** — paragraph-aware, overlapping windows, so meaning that straddles a boundary is
  never split away from its context.
- **Stable IDs** — every point is keyed by *(source, chunk index, content hash)*, independent of the
  absolute path, so re-ingesting the same content **updates in place** instead of creating duplicates.
- **Embeddings** — `fastembed` (default `BAAI/bge-small-en-v1.5`, 384-dim), or a zero-dependency
  `HashEmbedder` for a fully offline quick start.
- **Store** — Qdrant: `:memory:` (ephemeral), an embedded on-disk path (no server), or a remote URL.

## Zero-setup quick start (no model download)

```python
from ragpack import RAGpack, Settings

mill = RAGpack(Settings(model="hash", qdrant=":memory:"))   # deterministic, offline, no downloads
mill.ingest("./docs")
print(mill.search("your question")[0].source)
```

## Design notes

- **In-memory vs persistent.** A `:memory:` store lives inside one `RAGpack` instance — ingest and
  search on the *same* object. For separate processes (e.g. the CLI), use an on-disk path or a URL so
  the index persists between commands (the CLI defaults to `./ragpack_qdrant`).
- **Fail-closed GPU.** `device="cuda"` verifies `CUDAExecutionProvider` is actually available before
  embedding — no quiet, 10×-slower CPU fallback hiding in a "GPU" run.
- **Pluggable embedder.** `RAGpack(settings, embedder=...)` accepts any object with
  `dim`, `embed(texts)`, and `embed_one(text)` — swap in your own model or the built-in `HashEmbedder`.

## Install & test

```bash
pip install -e ".[dev]"
pytest -q
```

Zero-config tests run fully offline (the `HashEmbedder` + an in-memory Qdrant); CI runs them on
Python 3.10–3.12.

## License

MIT.
