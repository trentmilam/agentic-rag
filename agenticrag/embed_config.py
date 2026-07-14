"""Single source of truth for the embedder + Qdrant connection.

Both the ingest pipeline (writes vectors) and any future query-time module MUST use
the exact same model and device -- a mismatch produces silently meaningless cosine
scores with no error. Import SETTINGS/get_embedder/get_qdrant_client from here,
nowhere else.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ragpack.pipeline import Settings

AGENTIC_RAG_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = AGENTIC_RAG_ROOT / "data"


def _register_cuda_dll_dirs() -> None:
    """Windows only. onnxruntime-gpu 1.27.0 is built against CUDA 13.0 and looks for the
    CUDA/cuDNN DLLs under the pre-CUDA-13 per-component pip layout
    (``site-packages/nvidia/cublas/bin/...``, .../cuda_runtime/bin/..., .../cufft/bin/...).
    The nvidia-cublas / nvidia-cuda-runtime / nvidia-cufft wheels that actually ship CUDA 13
    content install under the unified ``site-packages/nvidia/cu13/bin/x86_64/`` layout
    instead, so onnxruntime can't find them and CUDAExecutionProvider silently fails to load
    (fastembed then falls back to CPU with no error, only a warning). Prepending both
    possible DLL directories to PATH lets Windows find the DLLs regardless of which layout
    is present; a no-op if the GPU extras (or CUDA build) aren't installed. (Registering the
    same directories via ``os.add_dll_directory`` instead was tried first and does NOT work
    here -- onnxruntime's CUDA provider bridge only picks up dependent DLLs that are on PATH.)
    """
    if sys.platform != "win32":
        return
    site_packages = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages"
    dirs = [site_packages / rel for rel in ("nvidia/cu13/bin/x86_64", "nvidia/cudnn/bin")]
    found = [str(d) for d in dirs if d.is_dir()]
    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dll_dirs()


def _normalize_qdrant(qdrant: str) -> str:
    """A relative AGENTICRAG_QDRANT override is otherwise resolved against whatever
    the *current process's* cwd happens to be -- two processes launched from
    different directories would silently open two different, unrelated on-disk
    stores. Absolute paths and the special :memory:/http(s):// forms pass through
    unchanged."""
    if not qdrant or qdrant == ":memory:" or qdrant.startswith(("http://", "https://")):
        return qdrant
    return str(Path(qdrant).resolve())


SETTINGS = Settings(
    model=os.environ.get("AGENTICRAG_EMBED_MODEL", "BAAI/bge-base-en-v1.5"),
    device=os.environ.get("AGENTICRAG_DEVICE", "auto"),
    qdrant=_normalize_qdrant(os.environ.get("AGENTICRAG_QDRANT", str(DATA_DIR / "qdrant"))),
    collection=os.environ.get("AGENTICRAG_COLLECTION", "agentic_rag"),
    ocr="never",  # this phase never runs OCR; scanned-procedure ingestion is a later phase
)


def get_embedder():
    """The one real embedder instance -- construct once, reuse across ingest+query."""
    from ragpack.embed import Embedder, HashEmbedder

    if (SETTINGS.model or "").strip().lower() == "hash":
        return HashEmbedder()
    return Embedder(SETTINGS.model, SETTINGS.device)


def get_qdrant_client():
    from ragpack.store import make_client

    return make_client(SETTINGS.qdrant)


def _marker_path() -> Path | None:
    """Where the "which model owns this collection" marker lives, or None for
    stores with no durable location to persist it (:memory:, a remote server)."""
    q = SETTINGS.qdrant
    if not q or q == ":memory:" or q.startswith(("http://", "https://")):
        return None
    return Path(q) / f"{SETTINGS.collection}.model.json"


def record_embedder_marker(*, recreate: bool = False) -> None:
    """Call once from the ingest path, right after ensure_collection(). Persists
    which model owns this collection so a later query-time process can catch a
    drift instead of silently computing meaningless cosine scores. On
    recreate=True the collection is genuinely fresh, so the marker is always
    (re)written; otherwise it's only written if this is the very first ingest."""
    marker = _marker_path()
    if marker is None:
        return
    if recreate or not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"model": (SETTINGS.model or "").strip()}), encoding="utf-8")
    else:
        verify_embedder_marker()


def verify_embedder_marker() -> None:
    """Call before querying. Raises if this process's configured model doesn't match
    the model that created the collection on disk -- the embedder-consistency
    contract this module's docstring promises, actually enforced."""
    marker = _marker_path()
    if marker is None or not marker.exists():
        return  # in-memory/remote store, or no ingest has run yet -- nothing to check
    recorded = json.loads(marker.read_text(encoding="utf-8")).get("model")
    model_name = (SETTINGS.model or "").strip()
    if recorded and recorded != model_name:
        raise ValueError(
            f"embedder mismatch: collection {SETTINGS.collection!r} at {SETTINGS.qdrant!r} "
            f"was ingested with model {recorded!r}, but this process is configured for "
            f"{model_name!r} -- query-time and ingest-time embedders must match exactly, "
            "or cosine scores are silently meaningless."
        )
