"""Qdrant vector store: zero-setup embedded by default, remote server when you scale.

``qdrant`` accepts:
- ``None`` / ``":memory:"`` → in-process, ephemeral (great for tests + quick trials),
- a filesystem path (e.g. ``"./ragpack_qdrant"``) → embedded, on-disk, no server,
- an ``http(s)://`` URL → a running Qdrant server.
"""
from __future__ import annotations

from typing import Any, Optional


def make_client(qdrant: Optional[str] = None):
    from qdrant_client import QdrantClient

    if not qdrant or qdrant == ":memory:":
        return QdrantClient(location=":memory:")
    if qdrant.startswith(("http://", "https://")):
        return QdrantClient(url=qdrant)
    return QdrantClient(path=qdrant)


def ensure_collection(client, collection: str, dim: int, recreate: bool = False) -> None:
    from qdrant_client.models import Distance, VectorParams

    if recreate and client.collection_exists(collection):
        client.delete_collection(collection)
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def upsert(client, collection: str, ids, vectors, payloads) -> None:
    from qdrant_client.models import PointStruct

    points = [
        PointStruct(id=i, vector=v, payload=p)
        for i, v, p in zip(ids, vectors, payloads)
    ]
    client.upsert(collection_name=collection, points=points)


def vector_search(client, collection: str, vector, limit: int, query_filter=None) -> list[Any]:
    """Return ranked points. Uses the modern ``query_points`` API, falling back to ``search``."""
    if hasattr(client, "query_points"):
        return list(
            client.query_points(
                collection_name=collection,
                query=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            ).points
        )
    return list(
        client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
    )
