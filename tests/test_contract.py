"""Contract validation: the EntityRef dataclass shape, and the
load_from_export <-> fixtures round trip through a real candidates.jsonl-
shaped file."""
import json

from linkgraph import fixtures
from linkgraph.adapter import load_from_export
from linkgraph.contract import EntityRef


def test_entity_ref_basic_fields():
    ref = EntityRef(
        entity_type="rfc", entity_id="RFCX9010", raw_text="text",
        doc_id="doc-1", resolved=True, extra={"obsoletes": ["RFCX9021"]},
    )
    assert ref.entity_type == "rfc"
    assert ref.entity_id == "RFCX9010"
    assert ref.extra == {"obsoletes": ["RFCX9021"]}


def test_entity_ref_extra_defaults_to_empty_and_is_not_shared():
    a = EntityRef("rfc", "1", "t", "d", True)
    b = EntityRef("rfc", "2", "t", "d", True)
    assert a.extra == {}
    a.extra["x"] = 1
    assert b.extra == {}  # default_factory=dict must not share one mutable dict


def test_load_from_export_round_trips_the_fixture(tmp_path):
    path = tmp_path / "candidates.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for ref in fixtures.FIXTURE_ENTITY_REFS:
            f.write(json.dumps({
                "entity_type": ref.entity_type,
                "entity_id": ref.entity_id,
                "raw_text": ref.raw_text,
                "doc_id": ref.doc_id,
                "resolved": ref.resolved,
                "extra": ref.extra,
            }) + "\n")

    loaded = load_from_export(str(path))
    assert loaded == fixtures.FIXTURE_ENTITY_REFS


def test_load_from_export_generic_over_entity_type(tmp_path):
    """The loader must not special-case any entity_type -- registry mentions
    (never cross-referenced elsewhere) load exactly like rfc/errata ones;
    it is resolve.build_graph's job to skip them, not the loader's."""
    path = tmp_path / "candidates.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "entity_type": "registry", "entity_id": "iana-ports",
            "raw_text": "IANA port registry", "doc_id": "registry-doc",
            "resolved": True, "extra": {},
        }) + "\n")

    loaded = load_from_export(str(path))
    assert len(loaded) == 1
    assert loaded[0].entity_type == "registry"


def test_load_from_export_skips_blank_lines(tmp_path):
    path = tmp_path / "candidates.jsonl"
    ref = fixtures.FIXTURE_ENTITY_REFS[0]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n")
        f.write(json.dumps({
            "entity_type": ref.entity_type, "entity_id": ref.entity_id,
            "raw_text": ref.raw_text, "doc_id": ref.doc_id,
            "resolved": ref.resolved, "extra": ref.extra,
        }) + "\n")
        f.write("   \n")

    loaded = load_from_export(str(path))
    assert loaded == [ref]
