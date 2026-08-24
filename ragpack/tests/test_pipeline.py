"""End-to-end ingest + search, fully offline: the HashEmbedder + an in-memory Qdrant.

Skips cleanly if qdrant-client isn't installed (so the pure-logic tests still run anywhere).
"""
import pytest

pytest.importorskip("qdrant_client")

from ragpack import RAGpack, Settings          # noqa: E402
from ragpack.pipeline import iter_files         # noqa: E402


def _corpus(tmp_path):
    (tmp_path / "backoff.md").write_text(
        "Retry logic uses exponential backoff with jitter to avoid thundering herds.",
        encoding="utf-8",
    )
    (tmp_path / "billing.md").write_text(
        "The billing module computes invoices monthly and emails a PDF receipt.",
        encoding="utf-8",
    )
    return tmp_path


def test_ingest_and_search_roundtrip(tmp_path):
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="t"))
    n = mill.ingest(_corpus(tmp_path))
    assert n >= 2
    hits = mill.search("exponential backoff retry", top_k=2)
    assert hits and hits[0].source == "backoff.md"   # the matching doc ranks first


def test_reingest_is_stable_no_duplicates(tmp_path):
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="t2"))
    corpus = _corpus(tmp_path)
    n1 = mill.ingest(corpus)
    n2 = mill.ingest(corpus)                          # same content -> same stable IDs
    assert n1 == n2
    assert mill.client.count(collection_name="t2").count == n1   # points didn't double


def test_iter_files_filters(tmp_path):
    (tmp_path / "keep.md").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.md").write_text("x", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01")
    names = {p.name for _, p in iter_files(tmp_path, max_file_bytes=1_000_000)}
    assert "keep.md" in names
    assert "dep.md" not in names        # node_modules skipped
    assert "blob.bin" not in names      # unsupported suffix


def test_ingest_under_skip_named_ancestor(tmp_path):
    # regression (stress #1): a corpus under a dir named like a skip-dir must still index
    root = tmp_path / "out" / "myproject"
    root.mkdir(parents=True)
    (root / "readme.md").write_text("exponential backoff retry logic " * 20, encoding="utf-8")
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="skipdir"))
    assert mill.ingest(root) >= 1
    assert mill.search("backoff")[0].source == "readme.md"


def test_distinct_roots_same_relpath_not_deduped(tmp_path):
    # regression (stress #2): two different files with the same relpath+content must NOT collapse
    content = "identical shared content forever " * 20
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "doc.md").write_text(content, encoding="utf-8")
    (b / "doc.md").write_text(content, encoding="utf-8")
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="tworoots"))
    mill.ingest([a, b])
    assert mill.client.count(collection_name="tworoots").count == 2


def test_search_top_k_nonpositive_returns_empty(tmp_path):
    # regression (stress #4/#5): top_k <= 0 -> empty, not the default 10
    (tmp_path / "d.md").write_text("hello world content " * 10, encoding="utf-8")
    mill = RAGpack(Settings(model="hash", qdrant=":memory:", collection="tk"))
    mill.ingest(tmp_path)
    assert mill.search("hello", top_k=0) == []
    assert mill.search("hello", top_k=-3) == []


def test_settings_reject_degenerate_values():
    # regression (stress #7/#8/#9/#11/#12): fail fast with a clear error, not a deep crash / silent 0
    for bad in (dict(batch_size=0), dict(batch_size=-1), dict(max_chars=0),
                dict(max_chars=100, overlap=100), dict(max_chars=100, overlap=200), dict(overlap=-1)):
        with pytest.raises(ValueError):
            Settings(model="hash", **bad)
