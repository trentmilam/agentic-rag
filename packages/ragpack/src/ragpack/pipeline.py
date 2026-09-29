"""High-level ingest + search: point ``ragpack`` at a folder, then query it.

The :class:`RAGpack` class holds one embedder + one Qdrant client, so an in-memory store
works end-to-end within a process (ingest then search see the same data). The module-level
:func:`ingest` / :func:`search` helpers are conveniences for a persistent store (path/URL).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from .chunk import chunk_text, classify_chunk, clean_text, content_hash, stable_id
from .embed import DEFAULT_MODEL, Embedder, HashEmbedder
from .evidence import EvidenceVerdict, evaluate_evidence
from .extract import extract_text
from .store import ensure_collection, make_client, upsert, vector_search

SKIP_DIRS = {
    ".git", ".github", "node_modules", "target", "build", "dist", "out", "vendor",
    "venv", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}

TEXT_SUFFIXES = {
    ".md", ".mdx", ".txt", ".rst", ".adoc", ".json", ".yaml", ".yml", ".toml", ".csv",
    ".html", ".htm", ".pdf",
    ".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".go", ".sol", ".c", ".cpp", ".cc",
    ".h", ".hpp", ".java", ".kt", ".swift", ".cs", ".sh", ".rb", ".php",
}

PathLike = Union[str, Path]


@dataclass
class Settings:
    """Runtime configuration (all fields overridable; env vars give the defaults)."""

    model: str = os.environ.get("RAGPACK_EMBED_MODEL", DEFAULT_MODEL)   # or "hash" (offline)
    device: str = os.environ.get("RAGPACK_DEVICE", "auto")               # auto|cpu|cuda
    qdrant: Optional[str] = os.environ.get("RAGPACK_QDRANT")             # None=:memory:, path, or URL
    collection: str = os.environ.get("RAGPACK_COLLECTION", "ragpack")
    max_chars: int = 1800
    overlap: int = 250
    batch_size: int = 64
    max_file_bytes: int = 2_000_000
    ocr: str = "auto"                                                    # auto|never|always

    def __post_init__(self):
        if self.max_chars < 1:
            raise ValueError("max_chars must be >= 1")
        if self.overlap < 0 or self.overlap >= self.max_chars:
            raise ValueError("overlap must be in [0, max_chars)")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be >= 1")
        if self.ocr not in ("auto", "never", "always"):
            raise ValueError("ocr must be one of auto|never|always")


@dataclass
class Hit:
    score: float
    text: str
    source: str
    payload: dict


@dataclass
class IngestRetryResult:
    hits: list[Hit]
    verdict: EvidenceVerdict
    hunted: bool
    docs_ingested: int


def iter_files(paths: Union[PathLike, Iterable[PathLike]], max_file_bytes: int):
    """Yield ``(root, file)`` for every supported, non-skipped, size-capped file under ``paths``."""
    roots = [paths] if isinstance(paths, (str, Path)) else list(paths)
    for raw in roots:
        root = Path(raw)
        explicit_file = root.is_file()
        candidates = [root] if explicit_file else sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            # Skip-dir filter applies ONLY to directories discovered *under* the crawl root, never
            # to the root/ancestors (a project living under .../out/ is fine) and never to a file the
            # caller named explicitly.
            if not explicit_file:
                try:
                    inner_dirs = set(path.relative_to(root).parts[:-1])
                except ValueError:
                    inner_dirs = set()
                if inner_dirs & SKIP_DIRS:
                    continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield root, path


def _payload(root: Path, path: Path, idx: int, chunk: str) -> tuple[dict, str]:
    try:
        rel = path.relative_to(root) if root.is_dir() else Path(path.name)
    except ValueError:
        rel = Path(path.name)
    rel_s = str(rel).replace("\\", "/")
    return (
        {
            "source": rel_s,
            "path": str(path).replace("\\", "/"),
            "chunk_index": idx,
            "chunk_type": classify_chunk(chunk, path.suffix),
            "char_count": len(chunk),
            "content_hash": content_hash(chunk),
            "text": chunk,
        },
        rel_s,
    )


class RAGpack:
    """Turns a folder of documents into a vector store you can ingest into and search, GPU-optional."""

    def __init__(self, settings: Optional[Settings] = None, embedder=None):
        self.settings = settings or Settings()
        self._embedder = embedder
        self._client = None

    @property
    def embedder(self):
        if self._embedder is None:
            if (self.settings.model or "").lower() == "hash":
                self._embedder = HashEmbedder()
            else:
                self._embedder = Embedder(self.settings.model, self.settings.device)
        return self._embedder

    @property
    def client(self):
        if self._client is None:
            self._client = make_client(self.settings.qdrant)
        return self._client

    def ingest(
        self,
        paths: Union[PathLike, Iterable[PathLike]],
        *,
        recreate: bool = False,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Extract → chunk → embed → upsert every supported file under ``paths``.

        Returns the number of chunks indexed. Re-ingesting the same content updates points
        in place (stable IDs), so it's safe to run repeatedly.
        """
        s = self.settings
        ensure_collection(self.client, s.collection, self.embedder.dim, recreate=recreate)

        records: list[tuple[int, str, dict]] = []
        for root, path in iter_files(paths, s.max_file_bytes):
            try:
                text = clean_text(extract_text(path, ocr=s.ocr))
            except Exception:
                continue
            for idx, chunk in enumerate(chunk_text(text, s.max_chars, s.overlap)):
                payload, rel = _payload(root, path, idx, chunk)
                pid = stable_id(str(root), rel, idx, payload["content_hash"])
                records.append((pid, chunk, payload))

        total = 0
        for start in range(0, len(records), s.batch_size):
            batch = records[start: start + s.batch_size]
            vectors = self.embedder.embed([r[1] for r in batch])
            upsert(self.client, s.collection, [r[0] for r in batch], vectors, [r[2] for r in batch])
            total += len(batch)
            if on_progress:
                on_progress(total, len(records))
        return total

    def search(self, query: str, *, top_k: int = 8) -> list[Hit]:
        """Embed ``query`` and return the ``top_k`` closest chunks (cosine)."""
        if top_k <= 0:
            return []
        vector = self.embedder.embed_one(query)
        points = vector_search(self.client, self.settings.collection, vector, top_k)
        hits: list[Hit] = []
        for point in points:
            payload = dict(getattr(point, "payload", None) or {})
            hits.append(
                Hit(
                    score=float(getattr(point, "score", 0.0) or 0.0),
                    text=str(payload.get("text", "")),
                    source=str(payload.get("source", "")),
                    payload=payload,
                )
            )
        return hits

    def ingest_and_retry(
        self,
        query: str,
        hunt_fn: Callable[[], Iterable[PathLike]],
        *,
        top_k: int = 8,
        min_hits: int = 1,
        min_top_score: float = 0.15,
    ) -> IngestRetryResult:
        """Search, and if the evidence is thin, ask ``hunt_fn`` for more content, ingest it, and
        search once more. Never retries a second time; this is a single hunt-and-retry, not a
        loop. ``hunt_fn`` takes no arguments and returns paths to newly-available content (or an
        empty iterable if it found nothing); it decides *how* to hunt, this method doesn't.
        """
        hits = self.search(query, top_k=top_k)
        verdict = evaluate_evidence(hits, min_hits=min_hits, min_top_score=min_top_score)
        if verdict.sufficient:
            return IngestRetryResult(hits=hits, verdict=verdict, hunted=False, docs_ingested=0)

        found = list(hunt_fn())
        if not found:
            return IngestRetryResult(hits=hits, verdict=verdict, hunted=True, docs_ingested=0)

        docs_ingested = self.ingest(found, recreate=False)
        hits = self.search(query, top_k=top_k)
        verdict = evaluate_evidence(hits, min_hits=min_hits, min_top_score=min_top_score)
        return IngestRetryResult(hits=hits, verdict=verdict, hunted=True, docs_ingested=docs_ingested)


def ingest(paths, settings: Optional[Settings] = None, *, recreate: bool = False,
           on_progress=None) -> int:
    """Convenience one-shot ingest. Use a persistent ``qdrant`` (path/URL) so a later
    :func:`search` sees the data; for an in-memory store, use one :class:`RAGpack` instance."""
    return RAGpack(settings).ingest(paths, recreate=recreate, on_progress=on_progress)


def search(query: str, settings: Optional[Settings] = None, *, top_k: int = 8) -> list[Hit]:
    """Convenience one-shot search (see :func:`ingest` note about in-memory stores)."""
    return RAGpack(settings).search(query, top_k=top_k)
