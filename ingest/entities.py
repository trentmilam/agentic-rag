"""The one entity-reference shape every connector's ``extract()`` emits.

A single flat type -- rather than a per-connector one -- is what lets ``candidates.jsonl``
be a uniform stream a later coverage-gap or conflict-detection tool can scan without
knowing which connector produced any given line.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EntityRef:
    entity_type: str  # "rfc" | "errata" | "registry"
    entity_id: str
    raw_text: str
    doc_id: str
    resolved: bool
    extra: dict = field(default_factory=dict)
