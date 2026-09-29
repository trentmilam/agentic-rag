"""Qdrant-native retrieval: the router's best-chunk signal and the composer's
top-k retrieval run as Qdrant vector searches instead of scanning every chunk in
Python.

consilium's Router (``_module_score``) and Module (``retrieve``) score the query
against *every* chunk in a module with a pure-Python cosine loop. On agentic-rag's
real 321k-chunk corpus that is minutes per query. consilium is deliberately
dependency-free ("no numpy, standalone") and is NOT modified here; instead
agentic-rag supplies its own Module/Router that push exactly those two O(N) loops
down into Qdrant (the store that already holds the vectors) while reusing
consilium's Router scoring formula, floor/anchor logic, composer, integrity gate,
and hardening unchanged.

Note on Qdrant local mode: it is an exact brute-force search (no ANN index), so a
search still scans the filtered subset, but in optimized native code, ~16x
faster than the pure-Python loop, and only the top-k are materialized. Sub-ms
search would require Qdrant server mode (HNSW); local mode keeps the repo
self-contained (no server to run) at ~seconds per search.

Poison-quarantine correctness: consilium's ``quarantine_poison`` corroborates a
retrieved chunk against ``module.chunks``. A chunk with no salient magnitude value
(``hardening._salient_values``) can neither corroborate (``_agree`` needs a shared
value) nor conflict (``_conflict`` needs both sides to have one), so it can never
change quarantine's output. So ``module.chunks`` here holds EXACTLY the salient
chunks (a few hundred out of 321k), loaded once at build: quarantine behaves
identically to the full-corpus version, without materializing the corpus.
"""
from __future__ import annotations


from consilium.embed import cosine, tokenize   # noqa: E402
from consilium.module import Chunk, Module      # noqa: E402
from consilium.router import Router             # noqa: E402

# The composer's k_per_module is small (2); search a few extra so best-chunk (top-1)
# and retrieve (top-k) share ONE cached search per query. Brute-force cost is
# ~independent of this limit (the scan dominates, not materializing k points).
_SEARCH_TOPK = 8


def _module_filter(source_type: str, current_only: bool):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    must = [FieldCondition(key="source_type", match=MatchValue(value=source_type))]
    if current_only:
        must.append(FieldCondition(key="is_current", match=MatchValue(value=True)))
    return Filter(must=must)


class QdrantModule(Module):
    """A consilium ``Module`` whose corpus lives in Qdrant, not Python memory.

    ``retrieve`` and the router's best-chunk signal are one Qdrant vector search
    (filtered by ``source_type`` + ``is_current``), memoized so routing's best-chunk
    call and the composer's retrieve call for the same query reuse a single search.
    ``chunks`` holds only the salient-value chunks (see module docstring) so
    consilium's poison-quarantine is exact. ``centroid()`` is inherited unchanged.
    """

    def __init__(self, descriptor, embedder, client, collection: str, source_type: str,
                 salient_chunks: list, *, current_only: bool = True) -> None:
        super().__init__(name=descriptor.name, descriptor=descriptor,
                         chunks=salient_chunks, embedder=embedder)
        self._client = client
        self._collection = collection
        self._source_type = source_type
        self._filter = _module_filter(source_type, current_only)
        self._cache_key = None
        self._cache_points: list = []

    def _search(self, query_vec) -> list:
        # Single-entry cache keyed by the query vector's VALUES: the router computes
        # query_vec and the composer recomputes it (a different list, identical
        # values), so a value key lets retrieve() reuse routing's search instead of
        # a second full scan of the same module.
        key = tuple(query_vec)
        if key != self._cache_key:
            resp = self._client.query_points(
                collection_name=self._collection, query=list(query_vec),
                query_filter=self._filter, limit=_SEARCH_TOPK,
                with_payload=True, with_vectors=True,
            )
            self._cache_key, self._cache_points = key, resp.points
        return self._cache_points

    def best_chunk_score(self, query_vec) -> float:
        pts = self._search(query_vec)
        return float(pts[0].score) if pts else 0.0

    def retrieve(self, query_vec, k: int = 3):
        out = []
        for p in self._search(query_vec)[:k]:
            payload = p.payload or {}
            out.append((
                Chunk(
                    id=f"{payload.get('doc_id')}#{payload.get('chunk_index')}",
                    doc=str(payload.get("doc_id")),
                    text=str(payload.get("text", "")),
                    vec=list(p.vector) if p.vector is not None else [],
                ),
                float(p.score),
            ))
        return out


class QdrantRouter(Router):
    """consilium.Router with the ONE O(N) hot path, the best-chunk cosine over
    every chunk, delegated to each module's Qdrant search.

    The score formula, floor, and anchor logic below MIRROR
    ``consilium.router.Router._module_score`` EXACTLY (kept deliberately in sync);
    the ONLY difference is where ``best`` comes from: a Qdrant search for a
    ``QdrantModule``, and the unchanged in-memory ``max`` for anything else (e.g. a
    ComputeModule, whose empty ``chunks`` give best=0, exactly as before).
    """

    def _module_score(self, module, query_vec, q_tokens):
        cen = cosine(query_vec, module.centroid())
        if hasattr(module, "best_chunk_score"):
            best = module.best_chunk_score(query_vec)
        else:
            best = max((cosine(query_vec, c.vec) for c in module.chunks), default=0.0)
        subj_tokens = set()
        for s in module.descriptor.subjects:
            subj_tokens |= set(tokenize(s))
        n_subj = len(q_tokens & subj_tokens)
        overlap = (n_subj / len(q_tokens)) if q_tokens else 0.0
        score = 0.45 * cen + 0.20 * best + 0.35 * overlap
        anchor = ((n_subj >= self.anchor_min_subjects)
                  or (cen >= self.anchor_centroid)
                  or (best >= self.anchor_best_chunk))
        return score, {
            "centroid": round(cen, 3),
            "best_chunk": round(best, 3),
            "subject_overlap": round(overlap, 3),
            "n_subj": n_subj,
            "anchor": anchor,
        }


def load_salient_chunks_by_source(client, collection: str, source_types, *,
                                  current_only: bool = True) -> dict:
    """Scan the collection ONCE (payload only) for chunks carrying a salient
    magnitude value, the only chunks that can affect consilium's poison-quarantine
    corroboration, and return ``{source_type: [Chunk, ...]}`` WITH vectors.

    Uses ``consilium.hardening._salient_values`` itself as the salience oracle, so
    the set is identical to what quarantine would consider (single source of truth,
    not a re-implemented regex that could drift).
    """
    from consilium.hardening import _salient_values

    wanted = set(source_types)
    meta: dict = {}  # point id -> (source_type, doc_id, chunk_index, text)
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection, scroll_filter=None, limit=16384,
            with_payload=True, with_vectors=False, offset=offset,
        )
        for p in points:
            payload = p.payload or {}
            source_type = payload.get("source_type")
            if source_type not in wanted:
                continue
            if current_only and payload.get("is_current") is not True:
                continue
            if _salient_values(payload.get("text", "")):
                meta[p.id] = (source_type, payload.get("doc_id"),
                              payload.get("chunk_index"), payload.get("text", ""))
        if offset is None:
            break

    out: dict = {st: [] for st in wanted}
    if meta:
        records = client.retrieve(
            collection_name=collection, ids=list(meta), with_vectors=True, with_payload=False,
        )
        vec_by_id = {r.id: r.vector for r in records}
        for pid, (source_type, doc_id, chunk_index, text) in meta.items():
            out[source_type].append(Chunk(
                id=f"{doc_id}#{chunk_index}", doc=str(doc_id), text=str(text),
                vec=list(vec_by_id.get(pid) or []),
            ))
    return out
