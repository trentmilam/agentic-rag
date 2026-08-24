"""Tests for activerag.hunt.

Hermetic: every test drops real files into a real ``tmp_path`` staging
directory and reads them back. No network, no live registry, no GPU -- matching
the no-live-dependency style of test_evidence/test_priority/test_telemetry.
"""
from __future__ import annotations

from pathlib import Path

from activerag.hunt import StagingDirHuntSource


def _drop(directory: Path, name: str, body: str = "content") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_is_a_zero_arg_hunt_fn_returning_dropped_paths(tmp_path):
    staging = tmp_path / "rfc_text"
    _drop(staging, "a.md")
    _drop(staging, "b.md")

    source = StagingDirHuntSource(staging, source_type="rfc_text")
    found = source()  # called with NO arguments -- the ingest_and_retry contract

    assert sorted(p.name for p in found) == ["a.md", "b.md"]
    assert all(isinstance(p, Path) and p.is_file() for p in found)


def test_missing_staging_dir_returns_empty_not_error(tmp_path):
    # The drop-zone need not exist yet -- that's "found nothing", not a crash.
    source = StagingDirHuntSource(tmp_path / "never_created", source_type="errata")

    assert source() == []


def test_empty_staging_dir_returns_empty(tmp_path):
    staging = tmp_path / "iana"
    staging.mkdir()

    source = StagingDirHuntSource(staging, source_type="iana")

    assert source() == []


def test_only_newly_dropped_files_are_returned_on_second_call(tmp_path):
    staging = tmp_path / "rfc_index"
    _drop(staging, "first.md")
    source = StagingDirHuntSource(staging, source_type="rfc_index")

    first_call = source()
    assert [p.name for p in first_call] == ["first.md"]

    # A second call with nothing new must return nothing -- the already-handed
    # file is not re-offered (the "newly-dropped" contract).
    assert source() == []

    # Drop a new file; only THAT one comes back on the next call.
    _drop(staging, "second.md")
    third_call = source()
    assert [p.name for p in third_call] == ["second.md"]


def test_first_call_treats_all_preexisting_files_as_new(tmp_path):
    staging = tmp_path / "s"
    _drop(staging, "x.txt")
    _drop(staging, "y.txt")

    source = StagingDirHuntSource(staging, source_type="s")

    assert sorted(p.name for p in source()) == ["x.txt", "y.txt"]


def test_suffix_filter_excludes_non_matching_files(tmp_path):
    staging = tmp_path / "s"
    _drop(staging, "keep.md")
    _drop(staging, "keep2.TXT")  # case-insensitive
    _drop(staging, "skip.tmp")
    _drop(staging, "skip.partial")

    source = StagingDirHuntSource(
        staging, source_type="s", suffixes={".md", "txt"}  # bare "txt" normalised
    )

    assert sorted(p.name for p in source()) == ["keep.md", "keep2.TXT"]


def test_no_suffix_filter_returns_every_file(tmp_path):
    staging = tmp_path / "s"
    _drop(staging, "a.md")
    _drop(staging, "b.weirdext")
    _drop(staging, "c")  # no extension at all

    source = StagingDirHuntSource(staging, source_type="s")  # suffixes=None

    assert sorted(p.name for p in source()) == ["a.md", "b.weirdext", "c"]


def test_subdirectories_are_ignored_flat_dropzone(tmp_path):
    staging = tmp_path / "s"
    staging.mkdir()
    (staging / "nested").mkdir()
    _drop(staging / "nested", "inside.md")  # a file one level down
    _drop(staging, "top.md")

    source = StagingDirHuntSource(staging, source_type="s")

    # Only the top-level file; the nested directory and its contents are skipped.
    assert [p.name for p in source()] == ["top.md"]


def test_ordering_is_deterministic_sorted(tmp_path):
    staging = tmp_path / "s"
    for name in ["c.md", "a.md", "b.md"]:
        _drop(staging, name)

    source = StagingDirHuntSource(staging, source_type="s")

    assert [p.name for p in source()] == ["a.md", "b.md", "c.md"]


def test_source_type_is_exposed_for_telemetry(tmp_path):
    source = StagingDirHuntSource(tmp_path / "s", source_type="rfc_text")

    # The orchestrator/telemetry reads this to label which source was hunted.
    assert source.source_type == "rfc_text"
