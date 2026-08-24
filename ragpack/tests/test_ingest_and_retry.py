"""ingest_and_retry: detect thin evidence, hunt once, retry once -- fully offline.

Skips cleanly if qdrant-client isn't installed (so the pure-logic tests still run anywhere).
"""
import pytest

pytest.importorskip("qdrant_client")

from ragpack import RAGpack, Settings   # noqa: E402


def _irrelevant_corpus(tmp_path):
    (tmp_path / "billing.md").write_text(
        "The billing module computes invoices monthly and emails a PDF receipt.",
        encoding="utf-8",
    )
    return tmp_path


def test_sufficient_evidence_skips_the_hunt(tmp_path):
    (tmp_path / "backoff.md").write_text(
        "Retry logic uses exponential backoff with jitter to avoid thundering herds.",
        encoding="utf-8",
    )
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="retry-ok"))
    mill.ingest(tmp_path)

    def _hunt_fn():
        raise AssertionError("hunt_fn must not be called when evidence is already sufficient")

    plain_hits = mill.search("exponential backoff retry", top_k=8)
    result = mill.ingest_and_retry("exponential backoff retry", _hunt_fn, top_k=8)

    assert result.hunted is False
    assert result.docs_ingested == 0
    assert result.verdict.sufficient is True
    assert result.hits == plain_hits


def test_hunt_finds_new_content_and_the_retry_sees_it(tmp_path):
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="retry-hunt"))
    mill.ingest(_irrelevant_corpus(tmp_path))   # nothing about the query is ingested yet

    staged_dir = tmp_path / "staged"
    staged_dir.mkdir()

    def _hunt_fn():
        found = staged_dir / "found.md"
        found.write_text(
            "Quantum entanglement teleportation experiment results were published in the journal.",
            encoding="utf-8",
        )
        return [found]

    result = mill.ingest_and_retry("quantum entanglement teleportation experiment", _hunt_fn, top_k=8)

    assert result.hunted is True
    assert result.docs_ingested >= 1
    assert result.verdict.sufficient is True   # the second search, not the fabricated first one
    assert result.hits and result.hits[0].source == "found.md"


def test_hunt_finds_nothing_returns_the_original_thin_result(tmp_path):
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="retry-empty"))
    mill.ingest(_irrelevant_corpus(tmp_path))

    def _hunt_fn():
        return []

    original = mill.search("quantum entanglement teleportation experiment", top_k=8)
    result = mill.ingest_and_retry("quantum entanglement teleportation experiment", _hunt_fn, top_k=8)

    assert result.hunted is True
    assert result.docs_ingested == 0
    assert result.verdict.sufficient is False
    assert result.hits == original   # unchanged -- nothing new was ingested, so re-search matches
