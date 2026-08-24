"""Deterministic text cleaning, chunking, stable IDs, and a light chunk classifier.

Pure standard library — no third-party deps, no I/O. Same input → same output, always.
"""
from __future__ import annotations

import hashlib
import json
import re


def clean_text(text: str) -> str:
    """Normalize newlines and collapse runs of whitespace; strip ends."""
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 1800, overlap: int = 250) -> list[str]:
    """Split text into ~``max_chars`` chunks with ``overlap`` carry-over.

    Prefers paragraph boundaries (blank lines); only hard-splits a single block that
    is itself larger than ``max_chars``. A trailing slice of each chunk is prepended
    to the next so retrieval never loses context that straddles a boundary.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    overlap = max(0, min(overlap, max_chars // 2))   # cap overlap at half the window -> step stays meaningful
    if not text:
        return []

    blocks = re.split(r"\n\s*\n", text)
    # Each entry pairs a piece with whether it still needs the generic "\n\n"
    # overlap-merge below (True), or already has its overlap baked in directly
    # from the source text (False). The second kind only occurs for a hard split's
    # 2nd+ tile: slicing a WIDER window straight out of the original block (instead
    # of gluing two independently-.strip()'d fragments back together) is the only
    # way to add overlap there without corrupting content -- gluing with "\n\n"
    # injects characters into what's really one unbroken run of text, corrupting a
    # word straddling the split point (e.g. "subse" + "\n\n" + "quent"); gluing with
    # no separator at all instead fuses two whole words that had a real space
    # between them ("word0388" + "word0389" -> "word0388word0389") because each
    # piece's OWN .strip() had already discarded that boundary space. A direct
    # slice of the source has neither problem -- it's just the literal text.
    raw: list[tuple[str, bool]] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current:
            raw.append((current, True))
            current = ""

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if len(current) + len(block) + 2 <= max_chars:
            current = f"{current}\n\n{block}".strip()
            continue

        flush_current()

        if len(block) <= max_chars:
            current = block
        else:
            starts = range(0, len(block), max_chars)
            for idx, start in enumerate(starts):
                if idx == 0:
                    piece = block[start: start + max_chars].strip()
                    if piece:
                        raw.append((piece, True))
                else:
                    piece = block[max(0, start - overlap): start + max_chars].strip()
                    if piece:
                        raw.append((piece, False))

    flush_current()

    if overlap <= 0 or len(raw) <= 1:
        return [piece for piece, _ in raw]

    with_overlap: list[str] = []
    prev_tail = ""
    for piece, needs_merge in raw:
        if needs_merge and prev_tail:
            merged = f"{prev_tail}\n\n{piece}".strip()
            with_overlap.append(merged[: max_chars + overlap])
        else:
            with_overlap.append(piece[: max_chars + overlap])
        prev_tail = with_overlap[-1][-overlap:]

    return with_overlap


def content_hash(text: str) -> str:
    """SHA-256 of the chunk text (used for change detection + stable IDs)."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def stable_id(source_id: str, relative_path: str, chunk_index: int, chash: str) -> int:
    """A deterministic, OS-path-independent Qdrant point ID.

    Hashes only (source_id, forward-slashed relative path, chunk index, content hash) —
    NOT the absolute path — so ingesting the same file from Windows and Linux produces the
    same point ID (re-ingest updates in place instead of creating duplicates).
    """
    id_payload = {
        "source_id": source_id,
        "relative_path": str(relative_path).replace("\\", "/"),
        "chunk_index": chunk_index,
        "content_hash": chash,
    }
    h = hashlib.sha256()
    h.update(json.dumps(id_payload, sort_keys=True, default=str).encode("utf-8"))
    return int.from_bytes(h.digest()[:8], "big", signed=False)


_CODE_SUFFIXES = {
    ".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".go", ".sol", ".cpp", ".cc", ".c",
    ".h", ".hpp", ".java", ".kt", ".swift", ".cs", ".sh", ".bash", ".rb", ".php",
}


def _blob_ratios(text: str) -> tuple[float, float]:
    """(long-blob ratio, code-line ratio) — used to flag machine-noise vs code vs prose."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0.0, 0.0
    blob = 0
    code = 0
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if re.search(r"[{}();=<>]", line) or re.match(
            r"^\s*(def|class|fn|func|function|const|let|var|struct|enum|impl|import|from|use|package)\b",
            line,
        ):
            code += 1
        if len(compact) < 80:
            continue
        if re.fullmatch(r"[0-9a-fA-F]{80,}", compact) or re.fullmatch(r"[A-Za-z0-9+/=]{100,}", compact):
            blob += 1
            continue
        symbols = sum(not (ch.isalnum()) for ch in compact)
        if len(compact) > 140 and symbols < len(compact) * 0.08:
            blob += 1
    total = max(len(lines), 1)
    return blob / total, code / total


def classify_chunk(text: str, suffix: str = "") -> str:
    """Coarse, domain-agnostic label: ``blob`` | ``code`` | ``table`` | ``prose``.

    Useful as a payload field for filtering (e.g. drop ``blob`` hex/base64 dumps, or
    boost ``code``). Deliberately generic — no domain vocabulary.
    """
    blob_ratio, code_ratio = _blob_ratios(text)
    if blob_ratio >= 0.35:
        return "blob"
    if suffix.lower() in _CODE_SUFFIXES or code_ratio >= 0.30 or re.search(
        r"```[a-zA-Z0-9+]*\n", text
    ):
        return "code"
    if text.count("|") >= 6 and re.search(r"\|.*\|.*\|", text):
        return "table"
    return "prose"
