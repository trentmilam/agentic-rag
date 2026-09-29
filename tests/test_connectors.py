"""Fixture-only tests for ``ingest.connectors.*``'s ``extract(path) -> ExtractedDoc``
output shape.

Each connector is exercised against a small, hand-written synthetic input file
written to ``tmp_path``, never a real fetched RFC/errata/IANA file, never the
321k-chunk corpus. This mirrors ``agenticrag/mcp/test_server.py``'s fixture-only
convention: no network, no Qdrant, no GPU, small synthetic inputs only.

Run under pytest:
    .venv/Scripts/python.exe -m pytest tests/test_connectors.py -q
"""
from __future__ import annotations

import pytest

from ingest.connectors import errata, iana_registry, rfc_index, rfc_text
from ingest.connectors.base import ExtractedDoc
from ingest.entities import EntityRef


# ---------------------------------------------------------------------------
# rfc_text.extract: full RFC text ingested verbatim
# ---------------------------------------------------------------------------
def test_rfc_text_extract_shape(tmp_path):
    body = (
        "Hypertext Transfer Protocol -- HTTP/1.1\n\n"
        "Status of this Memo\n\n"
        "This memo provides information for the Internet community.\n"
    )
    path = tmp_path / "rfc2616.txt"
    path.write_text(body, encoding="utf-8")

    doc = rfc_text.extract(path)

    assert isinstance(doc, ExtractedDoc)
    assert doc.doc_id == "rfc_text/rfc2616.txt"
    assert doc.source_type == "rfc_text"
    assert doc.text == body
    assert doc.part_number == "RFC2616"
    assert len(doc.entities) == 1
    entity = doc.entities[0]
    assert isinstance(entity, EntityRef)
    assert entity.entity_type == "rfc"
    assert entity.entity_id == "RFC2616"
    assert entity.raw_text == "RFC 2616"
    assert entity.doc_id == doc.doc_id
    assert entity.resolved is True


def test_rfc_text_extract_rejects_non_matching_filename(tmp_path):
    path = tmp_path / "not-an-rfc.txt"
    path.write_text("irrelevant", encoding="utf-8")

    with pytest.raises(ValueError):
        rfc_text.extract(path)


# ---------------------------------------------------------------------------
# rfc_index.extract: per-RFC "index card" rendered from rfc-index.txt
# ---------------------------------------------------------------------------
def test_rfc_index_extract_shape(tmp_path):
    card = (
        "RFC 2616 -- Hypertext Transfer Protocol -- HTTP/1.1\n"
        "Authors: R. Fielding, J. Gettys\n"
        "Date: June 1999\n"
        "Status: OBSOLETED\n"
        "Obsoletes: RFC 2068\n"
        "Obsoleted by: RFC 7230, RFC 7231, RFC 7232\n"
    )
    path = tmp_path / "rfc2616.txt"
    path.write_text(card, encoding="utf-8")

    doc = rfc_index.extract(path)

    assert doc.doc_id == "rfc_index/rfc2616.txt"
    assert doc.source_type == "rfc_index"
    assert doc.text == card
    assert doc.part_number == "RFC2616"
    assert len(doc.entities) == 1
    entity = doc.entities[0]
    assert entity.entity_type == "rfc"
    assert entity.entity_id == "RFC2616"
    assert entity.doc_id == doc.doc_id
    assert entity.resolved is True
    assert entity.extra["obsoletes"] == [2068]
    assert entity.extra["obsoleted_by"] == [7230, 7231, 7232]
    assert entity.extra["updates"] == []
    assert entity.extra["updated_by"] == []
    assert entity.extra["status"] == "OBSOLETED"


def test_rfc_index_extract_rejects_missing_header(tmp_path):
    path = tmp_path / "rfc9999.txt"
    path.write_text("Authors: nobody\nDate: never\n", encoding="utf-8")

    with pytest.raises(ValueError):
        rfc_index.extract(path)


def test_rfc_index_extract_rejects_empty_file(tmp_path):
    path = tmp_path / "rfc9999.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        rfc_index.extract(path)


# ---------------------------------------------------------------------------
# errata.extract: one real errata record (labeled header + correction body)
# ---------------------------------------------------------------------------
def test_errata_extract_shape(tmp_path):
    record = (
        "Errata ID: 1234\n"
        "RFC: RFC5322\n"
        "Status: Verified\n"
        "Type: Technical\n"
        "\n"
        "This is the body text of the correction.\n"
        "It spans two lines.\n"
    )
    path = tmp_path / "erratum_1234.txt"
    path.write_text(record, encoding="utf-8")

    doc = errata.extract(path)

    assert doc.doc_id == "errata/erratum_1234.txt"
    assert doc.source_type == "errata"
    assert doc.text == record
    assert doc.applies_to == "RFC5322"
    assert doc.part_number is None
    assert len(doc.entities) == 2

    errata_entity, rfc_entity = doc.entities
    assert errata_entity.entity_type == "errata"
    assert errata_entity.entity_id == "1234"
    assert errata_entity.resolved is True  # Status: Verified
    assert errata_entity.extra == {"status": "Verified", "type": "Technical", "rfc": "RFC5322"}

    assert rfc_entity.entity_type == "rfc"
    assert rfc_entity.entity_id == "RFC5322"
    assert rfc_entity.resolved is True


def test_errata_extract_unverified_status_is_unresolved(tmp_path):
    record = (
        "Errata ID: 4321\n"
        "RFC: RFC5321\n"
        "Status: Reported\n"
        "\n"
        "Some reported (not yet confirmed) correction.\n"
    )
    path = tmp_path / "erratum_4321.txt"
    path.write_text(record, encoding="utf-8")

    doc = errata.extract(path)

    errata_entity = doc.entities[0]
    assert errata_entity.resolved is False  # Status != "Verified"


# ---------------------------------------------------------------------------
# iana_registry.extract: IANA protocol-parameter registry XML -> markdown
# ---------------------------------------------------------------------------
def test_iana_registry_extract_shape(tmp_path):
    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<registry xmlns="http://www.iana.org/assignments" id="test-registry">\n'
        "  <title>Test Registry</title>\n"
        '  <registry id="section-1">\n'
        "    <title>Section One</title>\n"
        "    <record>\n"
        "      <name>foo</name>\n"
        "      <value>1</value>\n"
        "    </record>\n"
        "    <record>\n"
        "      <name>bar</name>\n"
        "      <value>2</value>\n"
        "    </record>\n"
        "  </registry>\n"
        "</registry>\n"
    )
    path = tmp_path / "test-registry.xml"
    path.write_text(xml_body, encoding="utf-8")

    doc = iana_registry.extract(path)

    assert doc.doc_id == "iana_registry/test-registry.xml"
    assert doc.source_type == "iana_registry"
    assert doc.part_number is None
    assert "# Test Registry (IANA registry)" in doc.text
    assert "## Section One" in doc.text
    assert "| name | value |" in doc.text
    assert "| foo | 1 |" in doc.text
    assert "| bar | 2 |" in doc.text

    assert len(doc.entities) == 1
    entity = doc.entities[0]
    assert entity.entity_type == "registry"
    assert entity.entity_id == "test-registry"  # path.stem
    assert entity.raw_text == "Test Registry"
    assert entity.doc_id == doc.doc_id
    assert entity.resolved is True
