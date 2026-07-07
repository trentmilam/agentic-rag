"""Append-only audit trail for a hunt-and-retry cycle.

RAGpack's ``ingest_and_retry`` (``projects/RAGpack/src/ragpack/pipeline.py``)
returns a single ``IngestRetryResult`` and forgets the attempt once the caller
is done with it. At the Consilium layer, "why did the hunt trigger, what did
it try, and did it help" is exactly the kind of thing a portfolio reviewer (or
a future debugging session) wants to replay after the fact -- so this module
gives every hunt cycle a durable, human-inspectable record.

This is intentionally a dumb recorder: it has ZERO import dependency on
``activerag.evidence`` (or anything else in this package). Verdict fields are
stored as plain ``dict``s -- a caller passes ``dataclasses.asdict(verdict)`` --
so this module never needs to know the shape of an ``EvidenceVerdict``, and
would keep working unchanged even if that shape changes.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SourceProbeRecord:
    source_type: str
    hunted: bool
    docs_found: int
    reason: str


@dataclass
class HuntEvent:
    ts: str
    query: str
    initial_verdict: dict
    sources_tried: list[SourceProbeRecord] = field(default_factory=list)
    winning_source: str | None = None
    docs_ingested: int = 0
    capped: bool = False
    final_verdict: dict = field(default_factory=dict)
    wall_clock_s: float = 0.0


def append_event(event: HuntEvent, path: Path) -> None:
    """Append ``event`` as one JSON line to ``path``. Creates parent
    directories if needed. Never truncates or rewrites existing lines --
    append-only, so the file is always safe to re-open across process runs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(event)) + "\n")


def read_events(path: Path) -> list[dict]:
    """Read every event back as a parsed dict, in append order. Returns an
    empty list if ``path`` does not exist yet -- that is a normal "no hunts
    recorded yet" state, not an error."""
    path = Path(path)
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events
