"""TEST FIXTURE modeling the real ``candidates.jsonl`` shape. NOT a claim
about any real, identifiable RFC. Every identifier below uses the ``RFCX``/
``ERRX`` prefix convention (matching ``rag-reliability/syncgate``'s and
``covgate``'s own fixtures): a real RFC citation is *always* exactly ``RFC``
followed by digits, with no letter in between, so ``RFCX<n>`` can never be
mistaken for, or collide with, a real, currently-assigned RFC, now or
after any number of future RFCs are issued. Every protocol described
("Widget Transport", "Session Handshake") is invented for this fixture.

Plain digit identifiers in the
"9000s" are not safe here. The real
RFC index (fetched into ``agentic-rag/data/raw/_cache/rfc-index.txt``) is
dense and sequential up to 10014 with no reliably permanent gaps, so RFC
9010, 9021-9026, and 9030 are real, currently-assigned RFCs (e.g. RFC 9010
is "Routing for RPL (Routing Protocol for Low-Power and Lossy Networks)
Leaves", RFC 9021 is "Use of the Walnut Digital Signature Algorithm...";
nothing like this fixture's invented Widget Transport / Session Handshake
content). Picking "a plausible-looking unused number" is not a reliable
safety property against a corpus assigned by an external authority that
keeps growing; only a non-digit-shaped identifier is permanently safe by
construction, which is why every fictional RFC-like id here is ``RFCX<n>``.
(Real errata IDs are already always purely numeric; see
``corpus_fetch/fetch_errata.py``'s ``/eid(\\d+)/`` pattern, so this
fixture's letter-prefixed ``ERRX<n>`` errata ids were never at risk of this
same collision, but use the same prefix convention for consistency.)

The fixture models a genuine small multi-obsoletes pattern shaped like the
real HTTP/1.1 case (RFC 2616 was later obsoleted by six separate RFCs,
7230-7235): a fictional monolithic ``RFCX9010`` is split into six independent
successors (``RFCX9021``-``RFCX9026``), plus a smaller two-successor split
(``RFCX9030`` splitting into ``RFCX9031``/``RFCX9032``) for a second,
independent family, plus a clarifying ``updates`` edge, three errata, one
intentionally DANGLING obsoletion pointer (``RFCX9022``'s obsoleted-by
target, ``RFCX9099``, is never given its own mention, modeling a real gap
where the ingest has not yet fetched/emitted a document a real RFC index
entry points at), and a handful of co-mention mentions grouped by
``doc_id`` for the weak co-occurrence signal.

Each RFC's raw text repeats that RFC's own subject-matter vocabulary
("multiplex"/"framing"/"stream"/"windowing"/"backpressure" for the Widget
Transport family; "handshake"/"certificate"/"cipher"/"nonce"/"attestation"
for the Session Handshake family), the same technique ``graphrx/fixtures.py``
itself uses to keep a family's facts genuinely coherent and two families
genuinely separable, which ``tests/test_graphrx_handoff.py`` exercises via a
planted cross-family merge.

Structured ``extra`` (obsoletes/updates/rfc) is attached only to each
entity's own canonical ("-index"/errata) mention, mirroring how a real
RFC-index-derived record would carry that metadata while a plain prose
reference to an already-known entity typically does not. ``resolve.py``'s
per-mention edge-building (rather than a separate "merge extras" step) is
what makes that split safe: every mention is processed independently and
redundant/duplicate edges are deduped by ``LinkGraph.add_edge``. ``extra``'s
cross-reference lists hold ``RFCX<n>`` strings here (the real contract from
agentic-rag's own connectors uses bare ints, since real RFC numbers are the
correct real-world representation); ``resolve.py`` reads them with plain
f-string interpolation, which works identically for either representation,
so this fixture-only divergence needs no production-code change.
"""
from __future__ import annotations

from .contract import EntityRef

FIXTURE_ENTITY_REFS: list[EntityRef] = [
    # ---- Widget Transport family (X9010 -> six successors, many-to-many) ----
    EntityRef(
        "rfc", "RFCX9010",
        "RFCX9010, Widget Transport Protocol: monolithic multiplex framing "
        "and stream windowing for widget delivery.",
        "rfcx-9010-index", True,
        {"obsoleted_by": ["RFCX9021", "RFCX9022", "RFCX9023", "RFCX9024", "RFCX9025", "RFCX9026"], "updated_by": ["RFCX9040"]},
    ),
    EntityRef(
        "rfc", "RFCX9021",
        "RFCX9021, Multiplexed Stream Framing: defines independent stream "
        "multiplex framing, obsoleting the monolithic model in RFCX9010.",
        "rfcx-9021-index", True, {"obsoletes": ["RFCX9010"]},
    ),
    EntityRef(
        "rfc", "RFCX9022",
        "RFCX9022, Stream Backpressure and Windowing: defines multiplexed "
        "stream backpressure signaling, obsoleting part of RFCX9010.",
        "rfcx-9022-index", True, {"obsoletes": ["RFCX9010"], "obsoleted_by": ["RFCX9099"]},
    ),
    EntityRef(
        "rfc", "RFCX9023",
        "RFCX9023, Multiplex Stream Prioritization: defines stream priority "
        "signaling for multiplexed transport, obsoleting RFCX9010.",
        "rfcx-9023-index", True, {"obsoletes": ["RFCX9010"]},
    ),
    EntityRef(
        "rfc", "RFCX9024",
        "RFCX9024, Multiplex Stream Flow Control: defines flow-control "
        "windowing for multiplexed streams, obsoleting RFCX9010.",
        "rfcx-9024-index", True, {"obsoletes": ["RFCX9010"]},
    ),
    EntityRef(
        "rfc", "RFCX9025",
        "RFCX9025, Multiplex Framing Extensions: extends stream multiplex "
        "framing headers, obsoleting RFCX9010.",
        "rfcx-9025-index", True, {"obsoletes": ["RFCX9010"]},
    ),
    EntityRef(
        "rfc", "RFCX9026",
        "RFCX9026, Multiplex Stream Security Considerations: documents "
        "security considerations for multiplexed stream framing, obsoleting "
        "RFCX9010.",
        "rfcx-9026-index", True, {"obsoletes": ["RFCX9010"]},
    ),
    EntityRef(
        "rfc", "RFCX9040",
        "RFCX9040, Widget Transport Clarifications: clarifies ambiguous "
        "multiplex framing text in RFCX9010.",
        "rfcx-9040-index", True, {"updates": ["RFCX9010"]},
    ),
    EntityRef(
        "errata", "ERRX100",
        "Erratum ERRX100 corrects a multiplex framing typo in RFCX9021's stream "
        "windowing section.",
        "errata-ERRX100", True, {"rfc": "RFCX9021", "status": "Verified"},
    ),
    EntityRef(
        "errata", "ERRX102",
        "Erratum ERRX102 corrects a stream windowing diagram in RFCX9010's "
        "multiplex framing appendix.",
        "errata-ERRX102", True, {"rfc": "RFCX9010", "status": "Verified"},
    ),
    # co-mention texture: one real doc discussing several of these together
    EntityRef(
        "rfc", "RFCX9021",
        "This document, RFCX9021, together with RFCX9022 and RFCX9023, "
        "replaces the monolithic multiplex framing defined in RFCX9010 with "
        "independent stream windowing, as corrected by Erratum ERRX100.",
        "rfcx-9021-body", True, {},
    ),
    EntityRef(
        "rfc", "RFCX9022",
        "RFCX9022 defines multiplexed stream backpressure and windowing "
        "alongside RFCX9021's stream framing, both superseding RFCX9010.",
        "rfcx-9021-body", True, {},
    ),
    EntityRef(
        "rfc", "RFCX9023",
        "RFCX9023 adds multiplex stream prioritization on top of the stream "
        "framing and windowing defined by RFCX9021 and RFCX9022.",
        "rfcx-9021-body", True, {},
    ),
    EntityRef(
        "errata", "ERRX100",
        "See Erratum ERRX100 for the corrected multiplex stream windowing "
        "text.",
        "rfcx-9021-body", True, {},
    ),
    # ---- Session Handshake family (X9030 -> two successors) ----
    EntityRef(
        "rfc", "RFCX9030",
        "RFCX9030, Session Handshake Protocol v1: defines the initial "
        "handshake certificate exchange and cipher negotiation.",
        "rfcx-9030-index", True, {"obsoleted_by": ["RFCX9031", "RFCX9032"]},
    ),
    EntityRef(
        "rfc", "RFCX9031",
        "RFCX9031, Handshake Cipher Suite Update: defines an updated "
        "handshake cipher negotiation with nonce attestation, obsoleting "
        "RFCX9030.",
        "rfcx-9031-index", True, {"obsoletes": ["RFCX9030"]},
    ),
    EntityRef(
        "rfc", "RFCX9032",
        "RFCX9032, Handshake Certificate Attestation: extends the handshake "
        "certificate exchange with nonce attestation, obsoleting RFCX9030.",
        "rfcx-9032-index", True, {"obsoletes": ["RFCX9030"]},
    ),
    EntityRef(
        "errata", "ERRX101",
        "Erratum ERRX101 corrects a cipher negotiation example in RFCX9031's "
        "handshake attestation appendix.",
        "errata-ERRX101", False, {"rfc": "RFCX9031", "status": "Reported"},
    ),
    # co-mention texture
    EntityRef(
        "rfc", "RFCX9030",
        "This document discusses RFCX9030's original handshake certificate "
        "exchange, later superseded by RFCX9031 and RFCX9032's cipher and "
        "attestation updates.",
        "rfcx-9030-body", True, {},
    ),
    EntityRef(
        "rfc", "RFCX9031",
        "RFCX9031 updates the handshake cipher negotiation with nonce "
        "attestation, as noted in Erratum ERRX101.",
        "rfcx-9030-body", True, {},
    ),
    EntityRef(
        "rfc", "RFCX9032",
        "RFCX9032 extends handshake certificate attestation alongside the "
        "cipher update in RFCX9031.",
        "rfcx-9030-body", True, {},
    ),
    EntityRef(
        "errata", "ERRX101",
        "Errata ERRX101 reports an issue in RFCX9031's handshake cipher "
        "negotiation example.",
        "rfcx-9030-body", False, {"rfc": "RFCX9031", "status": "Reported"},
    ),
]
