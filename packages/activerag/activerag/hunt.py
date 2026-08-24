"""A hunt source backed by a real local staging directory.

When :mod:`activerag.evidence` flags an answer as thin and the orchestrator (a
later task) decides to hunt, it needs something concrete to hand RAGpack's
``RAGpack.ingest_and_retry`` as its ``hunt_fn`` -- a
``Callable[[], Iterable[PathLike]]`` that takes no arguments and returns paths
to newly-available content (see ``projects/RAGpack/src/ragpack/pipeline.py``).

:class:`StagingDirHuntSource` is the simplest honest such source: it watches a
real local *staging directory* -- one directory per ``source_type`` -- into
which documents are dropped (by an operator, an upstream fetch job, an export
step -- this class does not care how). Each time it is called it returns the
paths of documents that have appeared since the last call, i.e. the
*newly-dropped* ones.

**Scope:** this is staging-directory-only. There is
deliberately NO internet-fetch / live-network hunt source here -- that is out of
scope. Everything this class does is a local filesystem read; it never touches
the network.

**"Newly-dropped" is per-instance, in-memory.** The instance remembers which
files it has already handed back and never returns the same file twice within
its own lifetime. On the FIRST call, every document already present is "new"
(nothing has been handed back yet). Seen-state lives only in the process; it is
not persisted across restarts (a fresh instance re-offers whatever is in the
directory). This matches the "did the hunt actually add anything" signal the
telemetry trail (:mod:`activerag.telemetry`) records: a hunt that returns
already-ingested files would report spurious new documents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Union

PathLike = Union[str, Path]


class StagingDirHuntSource:
    """A ``hunt_fn`` over one local staging directory.

    Args:
        staging_dir: the drop-zone directory this source watches. It need not
            exist yet -- until it does (or while it is empty), calls return an
            empty list, which is the contract's "found nothing" state, not an
            error.
        source_type: the logical source this staging dir represents (e.g.
            ``"rfc_text"``). Purely a label carried for the caller/telemetry
            (``SourceProbeRecord.source_type``); it does not affect discovery.
        suffixes: if given, only files whose lowercase extension is in this set
            are returned (e.g. ``{".md", ".txt"}``); comparison is
            case-insensitive and a leading dot is added if omitted. If ``None``
            (the default), every file in the directory is eligible.

    Call the instance with no arguments to get the newly-dropped documents:
    ``source = StagingDirHuntSource(dir, source_type="x"); paths = source()``.
    """

    def __init__(
        self,
        staging_dir: PathLike,
        *,
        source_type: str,
        suffixes: Optional[Iterable[str]] = None,
    ) -> None:
        self.staging_dir = Path(staging_dir)
        self.source_type = source_type
        self.suffixes = (
            None
            if suffixes is None
            else {self._normalize_suffix(s) for s in suffixes}
        )
        # Resolved paths already handed back, so the same file is never returned
        # twice. In-memory only -- see the module docstring.
        self._seen: set[Path] = set()

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        s = suffix.lower()
        return s if s.startswith(".") else "." + s

    def __call__(self) -> list[Path]:
        """Return the documents dropped into the staging directory that this
        instance has not already returned, in sorted (deterministic) order.

        Empty if the directory does not exist yet, is empty, or holds only files
        this instance has already handed back."""
        if not self.staging_dir.is_dir():
            return []

        found: list[Path] = []
        # Flat drop-zone: files are dropped directly into the directory. A
        # nested subdirectory is not a document and is skipped.
        for path in sorted(self.staging_dir.iterdir()):
            if not path.is_file():
                continue
            if self.suffixes is not None and path.suffix.lower() not in self.suffixes:
                continue
            resolved = path.resolve()
            if resolved in self._seen:
                continue
            self._seen.add(resolved)
            found.append(path)
        return found
