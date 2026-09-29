"""Load a Consilium Module directly from Qdrant: no re-embedding at startup.

The ingest pipeline (``ingest/run_ingest.py``) embeds every chunk ONCE and writes
it to Qdrant with ``source_type``/``is_current`` payload fields. This loader
reads those precomputed vectors+text back out, one Module per source type, so
Consilium's proven Router/compose() code runs completely unmodified: Qdrant is
the real embedding store, not a redundant side-index.

``current_only=True`` (the default) adds a second required Qdrant filter
condition (``is_current == True``) alongside ``source_type``. This is the
mechanism the revision guard is actually built on: a stale/superseded chunk
(e.g. a superseded procedure revision) literally never enters a Module's chunk
list, so it can never be retrieved or cited by that module. This is checkable by
construction (the query never touched the point), not a runtime heuristic
layered on top of ordinary retrieval.

MEASURED scroll-batch-size note: local-mode Qdrant's ``scroll()`` has a large,
roughly fixed per-call overhead (~2-4s) that dominates at small batch sizes:
at the naive ``limit=256`` that's ~8ms/point (a ~307k-chunk module takes
~45-50min); at ``limit=16384`` it's ~0.2ms/point (~1min for the same module).
This is a batch-size fix, not a selectivity one: ``count()`` returns in ~1.5s
for both a highly-selective and a near-unselective filter on this same
collection (confirmed). The cost was always the per-round-trip overhead of
returning many small pages of full points (payload+vectors), never the filter
evaluation itself.
"""
from __future__ import annotations

from consilium.module import Chunk, Descriptor, Module

_SCROLL_LIMIT = 16384


def load_module_from_qdrant(source_type: str, client, collection: str, embedder,
                             descriptor: Descriptor, *, current_only: bool = True) -> Module:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    must = [FieldCondition(key="source_type", match=MatchValue(value=source_type))]
    if current_only:
        must.append(FieldCondition(key="is_current", match=MatchValue(value=True)))
    flt = Filter(must=must)

    chunks: list[Chunk] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, scroll_filter=flt, limit=_SCROLL_LIMIT,
            with_payload=True, with_vectors=True, offset=offset,
        )
        for p in points:
            payload = p.payload or {}
            doc_id = payload.get("doc_id")
            chunk_index = payload.get("chunk_index")
            if doc_id is None or chunk_index is None:
                raise ValueError(
                    f"malformed Qdrant point {p.id!r} in collection {collection!r} "
                    f"(source_type={source_type!r}): missing doc_id/chunk_index in payload -- "
                    "the ingest that wrote this point is broken; re-run ingest, don't serve from it"
                )
            if p.vector is None:
                raise ValueError(
                    f"Qdrant point {p.id!r} (doc={doc_id!r}, source_type={source_type!r}) has no "
                    "vector -- a partial/failed upsert; re-run ingest for this document"
                )
            chunks.append(Chunk(
                id=f"{doc_id}#{chunk_index}",
                doc=str(doc_id),
                text=str(payload.get("text", "")),
                vec=list(p.vector),
            ))
        if offset is None:
            break
    if not chunks:
        raise ValueError(
            f"no Qdrant points found for source_type={source_type!r} "
            f"(current_only={current_only}) in collection={collection!r} -- "
            "run the ingest pipeline first"
        )
    return Module(name=descriptor.name, descriptor=descriptor, chunks=chunks, embedder=embedder)


def load_chunks_for_doc(doc_id: str, client, collection: str) -> list[Chunk]:
    """Targeted, doc_id-filtered chunk fetch for exactly ONE document. Proves
    a document's real Qdrant presence/absence without a full-module scroll.
    Deliberately ignores ``is_current`` (the revision guard needs to see a
    superseded document's chunks too, unfiltered by currency). No vectors
    fetched: this only answers presence/count/sample-text, never retrieval
    math. High selectivity (one document out of thousands) keeps this fast
    regardless of collection size, unlike a near-unselective module load,
    whose cost scales with round-trip count (see ``_SCROLL_LIMIT`` above)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
    chunks: list[Chunk] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, scroll_filter=flt, limit=1024,
            with_payload=True, with_vectors=False, offset=offset,
        )
        for p in points:
            payload = p.payload or {}
            chunks.append(Chunk(
                id=f"{payload.get('doc_id')}#{payload.get('chunk_index')}",
                doc=str(payload.get("doc_id")),
                text=str(payload.get("text", "")),
                vec=[],
            ))
        if offset is None:
            break
    return chunks
