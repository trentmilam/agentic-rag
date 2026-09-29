# RAGpack

**Mill your documents into a searchable vector store: GPU-optional embeddings, optional GPU OCR, Qdrant-backed.**

`RAGpack` turns a folder of documents (Markdown, code, text, and PDFs) into a semantic search
index in one line. It extracts text (with optional **GPU OCR** for scanned PDFs), chunks it with
overlap, embeds it on **CPU or CUDA**, and stores it in **Qdrant**: embedded on disk with zero
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
ragpack --qdrant ./data ingest ./docs
ragpack --qdrant ./data search "how does the retry logic work?"
```

## Install

Already installed as part of this repo: the root `pip install -e .` (see the top-level README
Quickstart) makes `import ragpack` resolve. The GPU/OCR extras are declared on this package's own
`pyproject.toml`, so install them from here:

```bash
cd packages/ragpack
pip install -e ".[gpu]"     # CUDA embeddings (fastembed-gpu + onnxruntime-gpu)
pip install -e ".[ocr]"     # + GPU OCR for scanned PDFs (docTR, uses CUDA when a CUDA PyTorch build is present)
```

## CPU or GPU: one switch

`device="auto"` (the default) uses CUDA when ONNX Runtime exposes a `CUDAExecutionProvider`, and
falls back to CPU otherwise. `device="cuda"` is **fail-closed**: it raises rather than silently
dropping to CPU, so a GPU run is always actually a GPU run. Set it in code, per-CLI-call (`--device`),
or via `RAGPACK_DEVICE`.

## What you get

Extraction covers plain text, code, and markdown, plus text-layer PDFs via `pypdf`; the `[ocr]`
extra adds scanned or image-only PDFs through docTR, GPU-accelerated automatically when a CUDA
PyTorch build is present (`ocr="auto"` only OCRs when the text layer is empty or garbled).
Chunking is paragraph-aware with overlapping windows, so meaning that straddles a boundary is never
split away from its context. Every point is keyed by *(source, chunk index, content hash)*,
independent of the absolute path, so re-ingesting the same content updates in place instead of
creating duplicates. Embeddings default to `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim), with a
zero-dependency `HashEmbedder` available for a fully offline quick start. The store is Qdrant, in
one of three modes: `:memory:` (ephemeral), an embedded on-disk path (no server), or a remote URL.

## Zero-setup quick start (no model download)

```python
from ragpack import RAGpack, Settings

mill = RAGpack(Settings(model="hash", qdrant=":memory:"))   # deterministic, offline, no downloads
mill.ingest("./docs")
print(mill.search("your question")[0].source)
```

## Design notes

A `:memory:` store lives inside one `RAGpack` instance, so ingest and search have to happen on the
*same* object. For separate processes (e.g. the CLI), use an on-disk path or a URL so the index
persists between commands (the CLI defaults to `./ragpack_qdrant`). The GPU path is fail-closed:
`device="cuda"` verifies `CUDAExecutionProvider` is actually available before embedding, so there
is no quiet, 10×-slower CPU fallback hiding inside a "GPU" run. The embedder is pluggable, too:
`RAGpack(settings, embedder=...)` accepts any object with `dim`, `embed(texts)`, and
`embed_one(text)`, so you can swap in your own model in place of the built-in `HashEmbedder`.

## Install & test

```bash
cd packages/ragpack   # if not already there
pip install -e ".[dev]"
pytest -q
```

Zero-config tests run fully offline (the `HashEmbedder` + an in-memory Qdrant); CI runs them on
Python 3.10–3.12.

## License

MIT.
