"""Fixture-only tests for ``agenticrag.registry_loader.load_module_from_qdrant``.

Built entirely against a hand-constructed fake Qdrant client -- no real
``qdrant_client.QdrantClient``, no on-disk collection, no network. Only
``qdrant_client.models`` (``FieldCondition``/``Filter``/``MatchValue``, plain
data-holder classes) is imported for real, exactly as ``registry_loader`` itself
does, so the ``scroll_filter`` the fake receives can be inspected with the real
shape the production code builds.

This covers the two things the loader's docstring calls out as the actual
mechanism the revision guard is built on: (1) precomputed vectors+text are
turned into a ``consilium.module.Module`` unmodified, and (2) ``current_only``
threads an ``is_current`` filter condition into the Qdrant query -- present
when True, absent when False.
"""
from __future__ import annotations

from consilium.module import Descriptor, Module

from agenticrag.registry_loader import load_module_from_qdrant


class FakePoint:
    """Stands in for a ``qdrant_client`` scroll result point: ``.id``,
    ``.payload`` (dict), ``.vector`` (list or None)."""

    def __init__(self, id, payload, vector):
        self.id = id
        self.payload = payload
        self.vector = vector


class FakeScrollClient:
    """Records every ``scroll_filter`` it is called with (for inspection) and
    hands back one fixed page of hand-built points, then signals "no more
    pages" via ``offset=None`` -- exactly enough of the real client's contract
    for ``load_module_from_qdrant``'s single while-loop to terminate after one
    call."""

    def __init__(self, points):
        self._points = points
        self.calls: list[dict] = []

    def scroll(self, *, collection_name, scroll_filter, limit, with_payload, with_vectors, offset=None):
        self.calls.append({
            "collection_name": collection_name,
            "scroll_filter": scroll_filter,
            "limit": limit,
            "with_payload": with_payload,
            "with_vectors": with_vectors,
            "offset": offset,
        })
        return self._points, None


def _make_points() -> list[FakePoint]:
    return [
        FakePoint(
            id="p1",
            payload={
                "doc_id": "rfc_text/rfc2616.txt", "chunk_index": 0,
                "text": "chunk one", "source_type": "rfc_text", "is_current": True,
            },
            vector=[0.1, 0.2],
        ),
        FakePoint(
            id="p2",
            payload={
                "doc_id": "rfc_text/rfc2616.txt", "chunk_index": 1,
                "text": "chunk two", "source_type": "rfc_text", "is_current": True,
            },
            vector=[0.3, 0.4],
        ),
    ]


def _descriptor() -> Descriptor:
    return Descriptor(name="rfc_text", subjects=["x"], example_queries=["y"])


def test_load_module_from_qdrant_builds_module_with_matching_chunks():
    client = FakeScrollClient(_make_points())

    module = load_module_from_qdrant(
        "rfc_text", client, "agentic_rag", embedder=object(), descriptor=_descriptor(),
    )

    assert isinstance(module, Module)
    assert module.name == "rfc_text"
    assert len(module.chunks) == 2
    assert module.chunks[0].id == "rfc_text/rfc2616.txt#0"
    assert module.chunks[0].doc == "rfc_text/rfc2616.txt"
    assert module.chunks[0].text == "chunk one"
    assert module.chunks[0].vec == [0.1, 0.2]
    assert module.chunks[1].id == "rfc_text/rfc2616.txt#1"
    assert module.chunks[1].text == "chunk two"
    assert module.chunks[1].vec == [0.3, 0.4]


def test_load_module_from_qdrant_keeps_descriptor_identity_and_collection_name():
    client = FakeScrollClient(_make_points())
    descriptor = _descriptor()

    module = load_module_from_qdrant(
        "rfc_text", client, "agentic_rag", embedder=object(), descriptor=descriptor,
    )

    assert module.descriptor is descriptor
    assert len(client.calls) == 1
    assert client.calls[0]["collection_name"] == "agentic_rag"


def test_current_only_true_adds_is_current_filter_condition():
    client = FakeScrollClient(_make_points())

    load_module_from_qdrant(
        "rfc_text", client, "agentic_rag", embedder=object(), descriptor=_descriptor(),
        current_only=True,
    )

    assert len(client.calls) == 1
    flt = client.calls[0]["scroll_filter"]
    keys = {cond.key for cond in flt.must}
    assert keys == {"source_type", "is_current"}

    source_cond = next(c for c in flt.must if c.key == "source_type")
    is_current_cond = next(c for c in flt.must if c.key == "is_current")
    assert source_cond.match.value == "rfc_text"
    assert is_current_cond.match.value is True


def test_current_only_false_omits_is_current_filter_condition():
    client = FakeScrollClient(_make_points())

    load_module_from_qdrant(
        "rfc_text", client, "agentic_rag", embedder=object(), descriptor=_descriptor(),
        current_only=False,
    )

    flt = client.calls[0]["scroll_filter"]
    keys = {cond.key for cond in flt.must}
    assert keys == {"source_type"}
    assert "is_current" not in keys
