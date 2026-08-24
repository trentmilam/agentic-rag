"""Tests for activerag.telemetry."""
from __future__ import annotations

import json

from activerag.telemetry import HuntEvent, SourceProbeRecord, append_event, read_events


def _make_event(query: str = "q1") -> HuntEvent:
    return HuntEvent(
        ts="2026-07-06T00:00:00Z",
        query=query,
        initial_verdict={"sufficient": False, "reason": "too_few_citations"},
        sources_tried=[
            SourceProbeRecord(source_type="local_a", hunted=True, docs_found=0, reason="empty"),
            SourceProbeRecord(source_type="local_b", hunted=True, docs_found=2, reason="found 2"),
        ],
        winning_source="local_b",
        docs_ingested=2,
        capped=False,
        final_verdict={"sufficient": True, "reason": "sufficient"},
        wall_clock_s=1.23,
    )


def test_appending_n_events_produces_exactly_n_lines(tmp_path):
    path = tmp_path / "sub" / "hunts.jsonl"

    for i in range(5):
        append_event(_make_event(query=f"q{i}"), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5


def test_each_line_is_valid_independently_parseable_json(tmp_path):
    path = tmp_path / "hunts.jsonl"

    for i in range(3):
        append_event(_make_event(query=f"q{i}"), path)

    lines = path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]  # raises if any line is bad JSON

    assert len(parsed) == 3
    assert [p["query"] for p in parsed] == ["q0", "q1", "q2"]
    assert parsed[0]["sources_tried"][1]["source_type"] == "local_b"


def test_reopen_and_append_preserves_earlier_events(tmp_path):
    path = tmp_path / "hunts.jsonl"

    append_event(_make_event(query="first"), path)
    append_event(_make_event(query="second"), path)
    events_after_two = read_events(path)

    append_event(_make_event(query="third"), path)
    events_after_three = read_events(path)

    assert [e["query"] for e in events_after_two] == ["first", "second"]
    assert [e["query"] for e in events_after_three] == ["first", "second", "third"]


def test_read_nonexistent_file_returns_empty_list_without_raising(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"

    assert read_events(path) == []
