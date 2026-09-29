"""Embeddings via fastembed, with a CPU / CUDA device switch.

- ``device="cpu"``  → fastembed on the ONNX Runtime CPU provider (the default install).
- ``device="cuda"`` → fastembed on ``CUDAExecutionProvider`` (needs the ``[gpu]`` extra:
  ``fastembed-gpu`` + ``onnxruntime-gpu`` + CUDA/cuDNN on PATH). Fails loudly if the GPU
  provider isn't actually available; it will NOT silently fall back to CPU.
- ``device="auto"`` → CUDA if available, else CPU.

The model default (``BAAI/bge-small-en-v1.5``, 384-dim) is small, fast, and strong for
retrieval; override via ``RAGPACK_EMBED_MODEL`` or the ``model`` argument.
"""
from __future__ import annotations

from typing import Iterable

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def _available_providers() -> list[str]:
    try:
        import onnxruntime as ort
        return list(ort.get_available_providers())
    except Exception:
        return []


def resolve_device(device: str = "auto") -> str:
    """Normalize a requested device to ``"cpu"`` or ``"cuda"``, honoring availability.

    Raises RuntimeError if ``cuda`` is explicitly requested but unavailable (fail-closed,
    so a GPU run never quietly degrades to CPU).
    """
    device = (device or "auto").strip().lower()
    if device in ("gpu", "cuda"):
        device = "cuda"
    elif device not in ("auto", "cpu"):
        raise ValueError(f"device must be auto|cpu|cuda, got {device!r}")

    cuda_ok = "CUDAExecutionProvider" in _available_providers()
    if device == "auto":
        return "cuda" if cuda_ok else "cpu"
    if device == "cuda" and not cuda_ok:
        raise RuntimeError(
            "device='cuda' requested but ONNX Runtime has no CUDAExecutionProvider. "
            "Install the GPU extra (`pip install RAGpack[gpu]`) and make sure CUDA + cuDNN "
            f"are on PATH. Available providers: {_available_providers()}"
        )
    return device


class Embedder:
    """Thin wrapper over ``fastembed.TextEmbedding`` exposing the resolved device + dim."""

    def __init__(self, model: str = DEFAULT_MODEL, device: str = "auto"):
        from fastembed import TextEmbedding

        self.model = model
        self.device = resolve_device(device)
        if self.device == "cuda":
            self._backend = TextEmbedding(
                model_name=model,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
        else:
            self._backend = TextEmbedding(model_name=model)
        # Probe once to learn the vector dimension (also surfaces a bad GPU setup early).
        self.dim = len(self.embed_one("dimension probe"))

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [
            v.tolist() if hasattr(v, "tolist") else list(v)
            for v in self._backend.embed(list(texts))
        ]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashEmbedder:
    """Deterministic, zero-dependency embeddings via the BLAKE2b hashing trick.

    No model download, no GPU, fully offline. Lower quality than a real model, but ideal
    for tests, CI, and a zero-setup quick start. Select with ``Settings(model="hash")`` or
    inject it directly into :class:`ragpack.RAGpack`.
    """

    def __init__(self, dim: int = 256, **_ignored):
        self.dim = dim
        self.device = "cpu"

    def embed(self, texts) -> list[list[float]]:
        import hashlib
        import math

        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in (text or "").lower().split():
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dim
                vec[idx] += 1.0 if (digest[4] & 1) else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
