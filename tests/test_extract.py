"""Extraction tests for the text-layer PDF path (pypdf is a base dependency, so this needs no
extra install). Scanned/image-only PDFs that require the docTR OCR path live in test_ocr.py,
which is skipped unless the `[ocr]` extra is installed.
"""
from ragpack.extract import extract_text, is_garbled


def _write_text_layer_pdf(path, text):
    """Hand-build the smallest valid one-page PDF whose content stream shows ``text`` via a
    Tj operator, so pypdf's real text-layer extraction runs against real PDF bytes -- no
    reportlab/fpdf dependency needed for a minimal fixture.
    """
    content = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    path.write_bytes(bytes(out))


def test_is_garbled():
    assert is_garbled("short")                       # below the min-chars floor
    assert not is_garbled("a real, readable sentence. " * 40)


def test_extract_text_reads_utf8_file(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("hello world", encoding="utf-8")
    assert extract_text(p) == "hello world"


def test_extract_text_missing_file_raises_filenotfound(tmp_path):
    # regression (stress #6): a missing .pdf must raise FileNotFoundError, not "install pypdf"
    import pytest
    with pytest.raises(FileNotFoundError):
        extract_text(tmp_path / "nope.pdf")
    with pytest.raises(FileNotFoundError):
        extract_text(tmp_path / "nope.txt")


def test_extract_text_reads_pdf_text_layer(tmp_path):
    # regression: the PDF text-layer path (_pypdf_text via extract_text) had zero coverage --
    # nothing ever exercised pypdf against a real PDF. 200+ printable chars keeps is_garbled()
    # False, proving the default ocr="auto" reads the text layer straight through and never
    # even attempts to import docTR (which isn't installed in this job -- see test_ocr.py).
    text = (
        "RAGpack extracts the text layer of a real PDF using pypdf. This sentence is padded "
        "well past the two hundred character floor so the garbled-text heuristic sees it as "
        "clean, readable prose rather than a failed extraction."
    )
    assert len(text) >= 200
    p = tmp_path / "doc.pdf"
    _write_text_layer_pdf(p, text)
    assert extract_text(p) == text
