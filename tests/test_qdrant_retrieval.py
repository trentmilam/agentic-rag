"""Fixture-only tests for the Qdrant-native retrieval layer
(``agenticrag.qdrant_retrieval``): ``QdrantModule`` (retrieve / best-chunk /
search memoization) and ``QdrantRouter._module_score`` (best-chunk delegated to
Qdrant for a QdrantModule, unchanged in-memory scan otherwise).

Built against a hand-built fake Qdrant client exposing ``query_points`` -- no real
Qdrant, no corpus, no network. Only ``consilium.embed.cosine`` (pure Python) is
used for real, to check the router's fallback path computes the same value.
"""
from __future__ import annotations

from consilium.embed import cosine
from consilium.module import Descriptor

from agenticrag.qdrant_retrieval import QdrantModule, QdrantRouter


class FakeScoredPoint:
    def __init__(self, id, score, payload, vector):
        self.id = id
        self.score = score
        self.payload = payload
        self.vector = vector


class FakeQueryResponse:
    def __init__(self, points):
        self.points = points


class FakeQueryClient:
    """Records every ``query_points`` call and returns a fixed page of points."""

    def __init__(self, points):
        self._points = points
        self.calls: list = []

    def query_points(self, *, collection_name, query, query_filter, limit,
                     with_payload, with_vectors):
        self.calls.append({"query": list(query), "limit": limit})
        return FakeQueryResponse(self._points)


def _desc(name="rfc_text"):
    return Descriptor(name=name, subjects=["internet protocol"], example_queries=["y"])


def _two_points():
    return [
        FakeScoredPoint("id1", 0.90,
                        {"doc_id": "rfc_index/rfc2616.txt", "chunk_index": 0, "text": "chunk A"},
                        [0.1, 0.2]),
        FakeScoredPoint("id2", 0.70,
                        {"doc_id": "rfc_index/rfc2616.txt", "chunk_index": 1, "text": "chunk B"},
                        [0.3, 0.4]),
    ]


def _module(client, salient_chunks=None):
    return QdrantModule(_desc(), embedder=object(), client=client, collection="c",
                        source_type="rfc_text", salient_chunks=salient_chunks or [])


def test_retrieve_maps_points_to_chunks_and_scores():
    m = _module(FakeQueryClient(_two_points()))
    out = m.retrieve([0.5, 0.5], k=2)
    assert [(c.id, c.text, c.vec, s) for c, s in out] == [
        ("rfc_index/rfc2616.txt#0", "chunk A", [0.1, 0.2], 0.90),
        ("rfc_index/rfc2616.txt#1", "chunk B", [0.3, 0.4], 0.70),
    ]


def test_retrieve_respects_k():
    m = _module(FakeQueryClient(_two_points()))
    assert len(m.retrieve([0.5, 0.5], k=1)) == 1


def test_best_chunk_score_is_top_point_score():
    m = _module(FakeQueryClient(_two_points()))
    assert m.best_chunk_score([0.5, 0.5]) == 0.90


def test_best_chunk_score_zero_when_no_points():
    m = _module(FakeQueryClient([]))
    assert m.best_chunk_score([0.5, 0.5]) == 0.0


def test_search_is_memoized_across_best_then_retrieve_for_same_query_values():
    client = FakeQueryClient(_two_points())
    m = _module(client)
    qv = [0.5, 0.5]
    m.best_chunk_score(qv)
    m.retrieve(list(qv), k=2)   # SAME values, DIFFERENT list object (router vs composer)
    assert len(client.calls) == 1  # one Qdrant search reused, not two full scans


def test_search_cache_misses_on_a_different_query():
    client = FakeQueryClient(_two_points())
    m = _module(client)
    m.best_chunk_score([0.5, 0.5])
    m.best_chunk_score([0.9, 0.1])
    assert len(client.calls) == 2


# --- QdrantRouter._module_score --------------------------------------------
class _FakeQdrantModule:
    """Exposes ``best_chunk_score`` (so the router delegates best-chunk to it) plus
    the ``centroid``/``descriptor`` the score formula needs."""

    def __init__(self, centroid_vec, best):
        self._cen = centroid_vec
        self._best = best
        self.descriptor = Descriptor(name="m", subjects=["internet protocol"], example_queries=[])
        self.chunks = []

    def centroid(self):
        return self._cen

    def best_chunk_score(self, query_vec):
        return self._best


class _FakeScanModule:
    """No ``best_chunk_score`` -- the router must fall back to the in-memory
    ``max(cosine over chunks)`` scan, exactly like consilium's base Router."""

    def __init__(self, centroid_vec, chunk_vecs):
        self._cen = centroid_vec
        self.descriptor = Descriptor(name="m", subjects=[], example_queries=[])
        self.chunks = [type("C", (), {"vec": v, "id": f"c{i}"})() for i, v in enumerate(chunk_vecs)]

    def centroid(self):
        return self._cen


def _router():
    return QdrantRouter(registry=None, embedder=None, floor=0.30,
                        anchor_centroid=0.45, anchor_best_chunk=0.97)


def test_router_uses_qdrant_best_chunk_score_when_available():
    module = _FakeQdrantModule(centroid_vec=[1.0, 0.0], best=0.83)
    score, bd = _router()._module_score(module, [1.0, 0.0], {"internet", "protocol"})
    assert bd["best_chunk"] == 0.83                 # taken from best_chunk_score, not a chunk scan
    assert bd["centroid"] == round(cosine([1.0, 0.0], [1.0, 0.0]), 3)  # == 1.0
    # score mirrors consilium's formula: 0.45*cen + 0.20*best + 0.35*overlap
    assert score == round(0.45 * 1.0 + 0.20 * 0.83 + 0.35 * 1.0, 4)


def test_router_falls_back_to_chunk_scan_without_best_chunk_score():
    module = _FakeScanModule(centroid_vec=[1.0, 0.0], chunk_vecs=[[1.0, 0.0], [0.0, 1.0]])
    _score, bd = _router()._module_score(module, [1.0, 0.0], set())
    expected_best = max(cosine([1.0, 0.0], v) for v in ([1.0, 0.0], [0.0, 1.0]))
    assert bd["best_chunk"] == round(expected_best, 3)  # == 1.0, from the in-memory scan
