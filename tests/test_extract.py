"""Extraction tests that don't need a PDF fixture or OCR deps."""
from ragpack.extract import extract_text, is_garbled


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
