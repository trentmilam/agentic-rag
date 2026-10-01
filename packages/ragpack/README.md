# RAGpack

Documents to a searchable vector store. GPU-optional embeddings, optional GPU OCR, Qdrant-backed.

- Input: Markdown, code, text, PDFs.
- Pipeline: extract (optional GPU OCR), chunk with overlap, embed on CPU or CUDA, store in Qdrant.
- Qdrant modes: `:memory:`, embedded on-disk path, remote URL.

```python
from ragpack import RAGpack, Settings

mill = RAGpack(Settings(qdrant="./data", device="auto"))   # CUDA if available, else CPU
mill.ingest("./docs")
for hit in mill.search("how does the retry logic work?"):
    print(f"{hit.score:.3f}  {hit.source}\n{hit.text[:200]}\n")
```

Shell:

```bash
ragpack --qdrant ./data ingest ./docs
ragpack --qdrant ./data search "how does the retry logic work?"
```

## Install

After the repo root `pip install -e .` (see the top-level README Quickstart), `import ragpack` resolves. Extras:

```bash
cd packages/ragpack
pip install -e ".[gpu]"     # CUDA embeddings (fastembed-gpu + onnxruntime-gpu)
pip install -e ".[ocr]"     # + GPU OCR for scanned PDFs (docTR, uses CUDA when a CUDA PyTorch build is present)
```

## Device

- `device="auto"` (default): CUDA if ONNX Runtime exposes `CUDAExecutionProvider`, else CPU.
- `device="cuda"`: raises if CUDA is unavailable. No CPU fallback.
- Set in code, `--device`, or `RAGPACK_DEVICE`.

## Features

- Extraction: text, code, markdown, text-layer PDFs (`pypdf`). `[ocr]` adds scanned PDFs via docTR. `ocr="auto"` OCRs only when the text layer is empty or garbled.
- Chunking: paragraph-aware, overlapping windows.
- Point key: *(source, chunk index, content hash)*, independent of absolute path. Re-ingest updates in place.
- Embeddings: `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim) by default. Zero-dependency `HashEmbedder` for offline use.
- Pluggable embedder: `RAGpack(settings, embedder=...)` takes any object with `dim`, `embed(texts)`, `embed_one(text)`.

## No model download

```python
from ragpack import RAGpack, Settings

mill = RAGpack(Settings(model="hash", qdrant=":memory:"))   # deterministic, offline, no downloads
mill.ingest("./docs")
print(mill.search("your question")[0].source)
```

`:memory:` lives in one `RAGpack` instance. For separate processes (the CLI), use an on-disk path or URL. The CLI defaults to `./ragpack_qdrant`.

## Tests

```bash
cd packages/ragpack   # if not already there
pip install -e ".[dev]"
pytest -q
```

Tests run offline (`HashEmbedder`, in-memory Qdrant). CI: Python 3.10-3.12.

## License

MIT.
