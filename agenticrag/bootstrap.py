"""build_registry(embedder, client=None) -> consilium.registry.Registry

Assembles agentic-rag's own Registry: one Consilium Module per real source
type in the ingested IETF corpus (rfc_text, rfc_index, errata, iana_registry),
each loaded straight from the shared Qdrant collection (see
``registry_loader.load_module_from_qdrant`` -- no re-embedding, no synthetic
fixtures), plus ``SupersessionModule``, a compute capability that answers the
one real question the retrieval modules alone cannot: which real RFC(s)
obsoleted a given one.

This is an entry file: it performs the sibling-path bootstrap (see
``_paths.py``) before importing anything from consilium.
"""
from __future__ import annotations


from consilium.module import Descriptor   # noqa: E402
from consilium.registry import Registry   # noqa: E402

from agenticrag.supersession import SupersessionModule           # noqa: E402

# Public (no leading underscore): eval/prove_revision_guard.py reuses these
# directly to load a standalone rfc_text module outside the registry.
DESCRIPTORS = {
    "rfc_text": Descriptor(
        name="rfc_text",
        subjects=[
            "IETF RFC full text", "internet protocol specification", "wire format",
            "TCP/IP", "HTTP", "SMTP", "DNS", "TLS", "IP addressing and fragmentation",
            "requirement keywords MUST SHOULD MAY",
        ],
        example_queries=[
            "How does IP fragmentation and reassembly work?",
            "What does a TCP header checksum protect against?",
            "What do MUST and SHOULD mean in an RFC?",
        ],
        authority="the primary IETF specification text itself (rfc-editor.org) -- "
                  "the normative source, not a summary of it",
        freshness="static snapshot of the CURRENT (non-obsoleted) RFC text as of "
                  "ingest date -- current_only=True structurally excludes an RFC's "
                  "own text once something obsoletes it (see registry_loader.py)",
        # Highest tier: this module's chunks ARE the normative spec text.
        trust_tier=0.95,
    ),
    "rfc_index": Descriptor(
        name="rfc_index",
        subjects=[
            "RFC metadata", "RFC authorship", "RFC publication date", "RFC document status",
            "which RFCs a document obsoletes or updates", "document history",
        ],
        example_queries=[
            "Who authored RFC 2119 and when was it published?",
            "What is the document status of RFC 5321?",
            "Which RFC numbers does RFC 3986 obsolete?",
        ],
        authority="the IETF RFC Editor's own rfc-index.txt catalog -- authoritative "
                  "metadata, one card per RFC",
        freshness="static snapshot of the live rfc-index.txt as of ingest date",
        # Authoritative metadata, but a rendered catalog card rather than the
        # normative text itself -- one tier below rfc_text.
        trust_tier=0.9,
    ),
    "errata": Descriptor(
        name="errata",
        subjects=[
            "RFC errata", "reported corrections to an RFC", "verified corrections",
            "editorial and technical errors", "errata resolution status",
        ],
        example_queries=[
            "What errata have been reported against RFC 5322?",
            "Has the erratum for RFC 5322 section 3.4.1 been verified?",
        ],
        authority="the IETF RFC Editor's own errata database (errata.rfc-editor.org) "
                  "-- real community-submitted corrections, each carrying its own "
                  "real disposition (see trust_tier note below)",
        freshness="static snapshot as of ingest date",
        # MEASURED (query data/entities/candidates.jsonl, entity_type=="errata",
        # n=5061 real errata records): Verified 2400 (47.4%), Held for Document
        # Update 1781 (35.2%), Rejected 679 (13.4%), Reported 201 (4.0%). Fewer
        # than half of real submitted errata are RFC-Editor-confirmed, and a
        # real ~13% are outright Rejected -- so this module corrects the
        # primary text but is not itself uniformly authoritative the way
        # rfc_text/rfc_index are; trust_tier sits well below both.
        trust_tier=0.55,
    ),
    "iana_registry": Descriptor(
        name="iana_registry",
        subjects=[
            "IANA protocol parameter registry", "registered port numbers",
            "media types", "HTTP status codes", "DNS parameters", "BGP parameters",
            "TLS parameters", "IPv4 address space allocation",
        ],
        example_queries=[
            "What port is registered for HTTPS?",
            "What is the registered media type for JSON?",
            "What does HTTP status code 404 mean?",
        ],
        authority="IANA's own protocol-parameter registries (iana.org) -- the "
                  "canonical registration authority, not a third-party mirror",
        freshness="static snapshot of the live IANA registries as of ingest date",
        trust_tier=0.9,
    ),
}

SUPERSESSION_DESCRIPTOR = Descriptor(
    name="supersession",
    subjects=[
        "RFC obsoletes", "RFC obsoleted by", "supersession", "which RFC replaced this one",
        "is this RFC still current", "RFC revision history graph",
    ],
    example_queries=[
        "What obsoleted RFC 2616?",
        "Is RFC 2616 still current?",
        "What RFCs replaced HTTP/1.1 (RFC 2616)?",
    ],
    authority="the real IETF Obsoletes/Obsoleted-by supersession graph "
              "(data/entities/revisions.json) -- a deterministic graph walk, no LLM",
    freshness="static snapshot of the live rfc-index.txt supersession graph as of "
              "ingest date",
    # A deterministic exact-graph lookup, not a heuristic -- same tier as
    # rfc_text's normative-source tier.
    trust_tier=0.95,
)

# consilium.router.Router's stated defaults (floor=0.11, anchor_centroid=0.25,
# anchor_best_chunk=0.25) assume a near-zero baseline cosine between unrelated
# text -- true for a bag-of-words HashEmbedder, false for a real dense embedder
# (BAAI/bge-base-en-v1.5) over this 321k-chunk corpus. MEASURED directly
# against this real corpus + real embedder (see eval/eval_agenticrag.py's
# printed calibration numbers, and agenticrag/calibrate.py which produced
# them): every genuine in-scope query's anchor module clears both a real
# centroid-cosine floor and a real subject-token-overlap floor well above the
# library defaults, while the out-of-scope probe never does -- but best-chunk
# cosine (a max over tens/hundreds of thousands of chunks per module) is a
# saturated order statistic that clears 0.25 for nearly any query, including
# the out-of-scope one, so it is not usable as an anchor signal at this
# corpus scale (the same finding holds at much smaller corpus scales too).
# These are per-instance Router kwargs for agentic-rag's own Router
# instantiation only; consilium's shared library defaults are untouched.
ROUTER_KWARGS = {"floor": 0.30, "anchor_centroid": 0.45, "anchor_best_chunk": 0.97}


def build_registry(embedder, client=None) -> Registry:
    """Assemble the 5-module Registry, backed by Qdrant.

    The 4 retrieval modules are :class:`~agenticrag.qdrant_retrieval.QdrantModule`s:
    they do NOT scroll the corpus into memory. Each answers the router's best-chunk
    signal and the composer's top-k retrieval with a live Qdrant vector search
    (local-mode brute-force, but ~16x the old pure-Python per-chunk scan and only
    the top-k materialized). Only the few hundred salient-value chunks are loaded
    once, for exact poison-quarantine (see ``qdrant_retrieval``). The 5th module is
    the in-process ``SupersessionModule``.

    Because the modules query Qdrant LIVE, the client is NOT closed here on success
    -- it lives for the caller's process (build a Router with :func:`build_router`,
    serve queries, let the process own the client). A client this function opened
    itself is closed only if the build FAILS; a caller-supplied client is always
    left to the caller.
    """
    from agenticrag.embed_config import (
        SETTINGS, get_qdrant_client, verify_embedder_marker,
    )
    from agenticrag.qdrant_retrieval import QdrantModule, load_salient_chunks_by_source

    # Fail LOUD if this process's configured embedder is not the one that
    # ingested the store -- otherwise every cosine score is silently meaningless
    # (see embed_config.verify_embedder_marker). This is the one place every
    # query entrypoint (app.py / run_demo.py / mcp.server) funnels through.
    verify_embedder_marker()

    created_client = client is None
    client = client or get_qdrant_client()
    try:
        # Pre-flight: a fresh clone ships no corpus (data/ is gitignored). Without
        # this, the scan below surfaces a raw qdrant_client exception; instead point
        # the user at the fetch+ingest quickstart.
        if not client.collection_exists(SETTINGS.collection):
            raise RuntimeError(
                f"Qdrant collection {SETTINGS.collection!r} does not exist at "
                f"{SETTINGS.qdrant!r}. This repo ships no corpus -- build it first:\n"
                "    python -m corpus_fetch.fetch_all\n"
                "    python ingest/run_ingest.py\n"
                "See the README \"Quickstart\" for the full sequence and expected runtime."
            )

        print("[build_registry] scanning for salient-value chunks "
              "(the exact corpus consilium's poison-quarantine needs)...", flush=True)
        salient = load_salient_chunks_by_source(client, SETTINGS.collection, list(DESCRIPTORS))

        modules = []
        total = len(DESCRIPTORS)
        for i, (source_type, descriptor) in enumerate(DESCRIPTORS.items(), start=1):
            n_salient = len(salient.get(source_type, []))
            print(f"[build_registry] module {i}/{total}: {source_type} "
                  f"(Qdrant-backed; {n_salient} salient chunks materialized)", flush=True)
            modules.append(QdrantModule(descriptor, embedder, client, SETTINGS.collection,
                                        source_type, salient.get(source_type, [])))
        modules.append(SupersessionModule(embedder, SUPERSESSION_DESCRIPTOR))
        print(f"[build_registry] {len(modules)} modules ready "
              "(Qdrant client stays open for live queries).", flush=True)
        registry = Registry(modules)
        # The QdrantModules query this client LIVE; the process owns it (released at
        # exit). Expose it so a consumer needing raw store access (e.g. the eval's
        # revision-guard doc fetch) REUSES it rather than opening a SECOND client --
        # Qdrant local mode allows only one opener per folder, and a second open
        # raises "already accessed by another instance".
        registry.qdrant_client = client
        return registry
    except Exception:
        if created_client:
            client.close()
        raise


def build_router(registry, embedder):
    """The Router every agentic-rag entrypoint serves with: a
    :class:`~agenticrag.qdrant_retrieval.QdrantRouter` (consilium's routing formula,
    best-chunk delegated to Qdrant) wired with this repo's measured ``ROUTER_KWARGS``
    calibration -- so the Qdrant-native path and the calibration always travel
    together."""
    from agenticrag.qdrant_retrieval import QdrantRouter

    return QdrantRouter(registry, embedder, **ROUTER_KWARGS)
