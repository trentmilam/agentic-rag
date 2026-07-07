"""Fixture-only tests for ``agenticrag.bootstrap.build_registry``'s wiring.

Built entirely against a hand-constructed fake Qdrant client -- no real
``qdrant_client``, no on-disk collection, no network, no GPU. The fake is
passed in as ``client=`` so ``build_registry``'s ``created_client`` stays
``False`` and it is never closed, and no real Qdrant store is ever opened.

Two things are made hermetic that ``build_registry`` would otherwise reach for
on real disk state:

* ``verify_embedder_marker()`` (from ``agenticrag.embed_config``) reads a
  small marker JSON next to ``SETTINGS.qdrant``; pointing ``SETTINGS.qdrant``
  at an empty ``tmp_path`` (no marker file there) makes it a no-op, exactly as
  it is for a fresh clone / an in-memory store.
* ``SupersessionModule`` (constructed unconditionally inside
  ``build_registry``) reads ``data/entities/revisions.json`` lazily via the
  module-level ``agenticrag.supersession._DEFAULT_REVISIONS_PATH`` constant.
  Monkeypatching that constant to a tiny synthetic revisions file avoids ever
  touching the real (321k-chunk-corpus-adjacent) supersession graph on disk.
"""
from __future__ import annotations

import json

import pytest
from consilium.registry import Registry
from ragpack.embed import HashEmbedder

import agenticrag.embed_config as embed_config
import agenticrag.supersession as supersession_mod
from agenticrag.bootstrap import build_registry


class FakePoint:
    def __init__(self, id, payload, vector):
        self.id = id
        self.payload = payload
        self.vector = vector


class FakeBootstrapClient:
    """``collection_exists`` is a fixed bool; ``scroll`` (called by the build's
    salient-value scan with ``scroll_filter=None``) returns every canned point in
    one page, then signals "no more pages" via ``offset=None``. ``close()`` is
    tracked so the "caller-owned client is left open" contract is checkable. No
    ``query_points`` here: the build never queries -- modules do that live at query
    time (see tests/test_qdrant_retrieval.py for that path)."""

    def __init__(self, points_by_source_type, *, exists):
        self._points_by_source_type = points_by_source_type
        self._exists = exists
        self.scroll_calls: list = []
        self.closed = False

    def collection_exists(self, name):
        return self._exists

    def scroll(self, *, collection_name, scroll_filter, limit, with_payload, with_vectors, offset=None):
        self.scroll_calls.append(scroll_filter)
        all_points = [p for pts in self._points_by_source_type.values() for p in pts]
        return all_points, None

    def close(self):
        self.closed = True


def _points_for(source_type: str, doc_id: str) -> list[FakePoint]:
    return [
        FakePoint(
            id=f"{doc_id}#0",
            payload={
                "doc_id": doc_id, "chunk_index": 0, "text": f"{source_type} chunk",
                "source_type": source_type, "is_current": True,
            },
            vector=[0.1, 0.2, 0.3],
        ),
    ]


@pytest.fixture(autouse=True)
def _hermetic_qdrant_marker(monkeypatch, tmp_path):
    """No fresh-clone/dirty-machine dependency: point the embedder-marker
    check at an empty directory (no marker file there) so
    ``verify_embedder_marker()`` always no-ops, regardless of what this
    developer's own ``data/qdrant/`` happens to contain."""
    monkeypatch.setattr(embed_config.SETTINGS, "qdrant", str(tmp_path))


@pytest.fixture
def _synthetic_revisions(monkeypatch, tmp_path):
    """Point SupersessionModule's lazy revisions-graph load at a tiny
    synthetic file instead of the real data/entities/revisions.json."""
    revisions_path = tmp_path / "revisions.json"
    revisions_path.write_text(
        json.dumps({"RFC1": {
            "obsoletes": [], "obsoleted_by": [], "status": "CURRENT", "title": "Synthetic",
        }}),
        encoding="utf-8",
    )
    monkeypatch.setattr(supersession_mod, "_DEFAULT_REVISIONS_PATH", revisions_path)
    return revisions_path


def test_build_registry_assembles_five_modules_from_fake_client(_synthetic_revisions):
    points_by_source_type = {
        "rfc_text": _points_for("rfc_text", "rfc_text/rfc2616.txt"),
        "rfc_index": _points_for("rfc_index", "rfc_index/rfc2616.txt"),
        "errata": _points_for("errata", "errata/erratum_1.txt"),
        "iana_registry": _points_for("iana_registry", "iana_registry/test.xml"),
    }
    client = FakeBootstrapClient(points_by_source_type, exists=True)
    embedder = HashEmbedder()

    registry = build_registry(embedder, client=client)

    assert isinstance(registry, Registry)
    names = {m.name for m in registry.modules}
    assert names == {"rfc_text", "rfc_index", "errata", "iana_registry", "supersession"}
    assert len(registry.modules) == 5
    # A caller-supplied client is never closed by build_registry.
    assert client.closed is False
    # The live client is exposed on the registry so a consumer needing raw store
    # access reuses it instead of opening a SECOND client (Qdrant local mode is
    # single-opener per folder -- a second open raises).
    assert registry.qdrant_client is client


def test_build_registry_raises_runtime_error_when_collection_missing():
    client = FakeBootstrapClient({}, exists=False)
    embedder = HashEmbedder()

    with pytest.raises(RuntimeError) as exc_info:
        build_registry(embedder, client=client)

    message = str(exc_info.value)
    assert "fetch_all" in message
    assert "run_ingest" in message
    assert "Quickstart" in message
    # The pre-flight fires before any module load is attempted.
    assert client.scroll_calls == []
    assert client.closed is False
