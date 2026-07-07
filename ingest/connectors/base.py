"""The one extraction result every connector's ``extract(path)`` returns.

``part_number`` stays ``None`` for documents that aren't intrinsically about one RFC
(an IANA registry, spanning many protocols at once); a connector sets it only when the
whole file is about one specific RFC (its full text, its index card). ``revision``/``supersedes`` are unused in this domain -- an RFC has no revision of its
own, a new number entirely replaces it -- and are kept only because ``applies_to``
(set by the errata connector to the RFC number an erratum corrects) shares this same
result shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ingest.entities import EntityRef


@dataclass
class ExtractedDoc:
    doc_id: str
    source_type: str
    text: str
    entities: list[EntityRef] = field(default_factory=list)
    part_number: str | None = None
    revision: str | None = None
    applies_to: str | None = None
    supersedes: str | None = None
