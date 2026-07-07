"""Text extraction from files, with optional GPU OCR for scanned PDFs.

- Plain text / code / markdown → read as UTF-8.
- Text-layer PDFs → ``pypdf``.
- Scanned / image-only PDFs → optional OCR via docTR (``[ocr]`` extra), which runs on the
  GPU automatically when PyTorch sees CUDA. Controlled by ``ocr``:
    * ``"auto"``   → OCR only when the text layer is empty/garbled (the default),
    * ``"always"`` → always OCR the PDF,
    * ``"never"``  → text layer only.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

MIN_TEXT_CHARS = 200
MAX_BINARY_RATIO = 0.30


def is_garbled(text: str) -> bool:
    """True if ``text`` is too short or mostly non-printable (a failed text-layer read)."""
    if len(text) < MIN_TEXT_CHARS:
        return True
    non_printable = sum(1 for ch in text if not ch.isprintable() and ch not in "\n\r\t")
    return (non_printable / max(len(text), 1)) > MAX_BINARY_RATIO


def _pypdf_text(path: Path) -> str:
    try:
        import pypdf
    except ImportError as exc:  # pragma: no cover - pypdf is a base dependency
        raise RuntimeError("pypdf is required to read PDFs (`pip install RAGpack`)") from exc
    try:
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _ocr_model():
    try:
        from doctr.models import ocr_predictor
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires the [ocr] extra: `pip install RAGpack[ocr]` "
            "(docTR + a PyTorch build; uses the GPU automatically when CUDA is present)."
        ) from exc
    # docTR picks CUDA automatically if the torch build sees a GPU; CPU otherwise.
    return ocr_predictor(pretrained=True)


def ocr_pdf(path: Path) -> str:
    """OCR a PDF with docTR. Requires the ``[ocr]`` extra. GPU-accelerated when available."""
    from doctr.io import DocumentFile

    doc = DocumentFile.from_pdf(str(path))
    return _ocr_model()(doc).render()


def extract_text(path: str | Path, ocr: str = "auto") -> str:
    """Return the plain text of a file. PDFs use the text layer, then OCR per ``ocr``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ragpack: no such file: {path}")
    if path.suffix.lower() == ".pdf":
        text = _pypdf_text(path)
        if ocr == "always" or (ocr == "auto" and is_garbled(text)):
            ocr_text = ocr_pdf(path)
            if len(ocr_text) > len(text):
                text = ocr_text
        return text
    return path.read_text(encoding="utf-8", errors="replace")
