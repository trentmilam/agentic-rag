"""The ``candidates.jsonl`` contract: one ``EntityRef`` per extracted entity
MENTION (not one per entity -- an entity like ``rfc:RFCX9010`` may be mentioned on
several lines, once per source document/chunk it appears in).

This mirrors agentic-rag's real ingest output shape exactly (see that repo's
``ingest/entities.py``), documented here independently so linkgraph can be
built and fully tested against hand-built fixtures before that pipeline's real
network fetch finishes -- then point ``adapter.load_from_export`` at the real
file with no code change, per the "documented, swappable loader" design.

Field semantics worth calling out because they are genuinely overloaded across
entity types (this overloading comes from the source contract, not invented
here):

* ``entity_type`` -- ``"rfc"`` | ``"errata"`` | ``"registry"``. linkgraph only
  builds graph structure from ``"rfc"`` and ``"errata"``; ``"registry"``
  entities (one per IANA registry file) are never cross-referenced by anything
  else in the corpus, so ``resolve.build_graph`` skips them on purpose --  see
  that module's docstring.
* ``resolved`` -- for ``entity_type="rfc"`` this is the ordinary entity-
  resolution-succeeded flag. For ``entity_type="errata"`` the source contract
  repurposes it as the erratum's real status: ``True`` means a ``Verified``
  erratum, ``False`` means ``Reported``/unverified. linkgraph does not
  normalize this away -- it is read for whichever meaning applies to that
  mention's ``entity_type``.
* ``extra`` -- for ``"rfc"``: ``{"obsoletes": [...], "obsoleted_by": [...],
  "updates": [...], "updated_by": [...]}``, each a list of RFC numbers (int).
  For ``"errata"``: ``{"rfc": <rfc number>, "status": "Verified" |
  "Reported"}`` (key names match the real ingest's errata connector, confirmed
  against ``agentic-rag/data/entities/candidates.jsonl`` --
  ``resolve.py`` is the one place that would need updating if that ever
  changes). Missing keys are
  always treated as absent/empty, never as an error -- a given mention need not
  carry every key (e.g. a plain-prose reference to an already-resolved RFC
  typically carries no structured ``extra`` at all).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntityRef:
    """One line of ``candidates.jsonl``: one extracted entity mention."""

    entity_type: str
    entity_id: str
    raw_text: str
    doc_id: str
    resolved: bool
    extra: dict[str, Any] = field(default_factory=dict)
