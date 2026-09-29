"""Scanned or image-only PDF, run through docTR OCR, end-to-end against a real (synthetic) fixture.

Skips cleanly if docTR isn't installed (the `[ocr]` extra: `pip install -e ".[ocr]"`), so the
base test job stays fast and dependency-light. CI runs this for real in a dedicated `ocr` job
(see .github/workflows/ci.yml) since it's the only way to actually prove the OCR path works
rather than just asserting it by inspection.
"""
import pytest

pytest.importorskip("doctr")

from PIL import Image, ImageDraw  # noqa: E402

from ragpack.extract import extract_text, is_garbled  # noqa: E402


def _write_scanned_pdf(path, text):
    """A one-page, image-only PDF (no text layer): what a real scanner/phone-camera capture
    looks like. Built with Pillow (already a docTR dependency), not a real/sensitive document.
    """
    img = Image.new("RGB", (600, 200), "white")
    ImageDraw.Draw(img).text((20, 80), text, fill="black")
    img.convert("RGB").save(path, "PDF")


def test_extract_text_ocrs_a_scanned_pdf(tmp_path):
    p = tmp_path / "scanned.pdf"
    _write_scanned_pdf(p, "RAGPACK OCR TEST DOCUMENT")

    # sanity: this fixture genuinely has no text layer, so extract_text must OCR it to pass
    assert is_garbled(extract_text(p, ocr="never"))

    text = extract_text(p, ocr="auto")
    assert "RAGPACK" in text.upper()
    assert "TEST" in text.upper()
    assert "DOCUMENT" in text.upper()
