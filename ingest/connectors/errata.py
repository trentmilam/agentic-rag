"""A real, community-submitted RFC erratum.

Each ``erratum_<id>.txt`` under ``data/raw/errata/`` is one record from the real
IETF errata database (``errata.rfc-editor.org``), rendered by
``corpus_fetch.fetch_errata`` as a small labeled-field header followed by the actual
correction text.

``resolved`` mirrors the old procedures connector's resolved/unresolved distinction,
but on a REAL status instead of a fabricated one: ``Verified`` means the RFC Editor
confirmed the correction is real, so ``resolved=True``; anything else (``Reported``,
``Held for Document Update``, ``Rejected``) has not been accepted as a confirmed fix,
so ``resolved=False``: a genuinely real "still needs attention / not authoritative"
case, not an invented one.
"""
from __future__ import annotations

from pathlib import Path

from ingest.connectors.base import ExtractedDoc
from ingest.entities import EntityRef


def extract(path: Path) -> ExtractedDoc:
    text = path.read_text(encoding="utf-8")
    doc_id = f"errata/{path.name}"
    lines = text.splitlines()

    fields: dict[str, str] = {}
    body_start = len(lines)
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        label, sep, value = line.partition(": ")
        if sep:
            fields[label.strip()] = value.strip()
    body = "\n".join(lines[body_start:]).strip()

    errata_id = fields.get("Errata ID", path.stem.replace("erratum_", ""))
    rfc_id = fields.get("RFC", "")
    status = fields.get("Status", "")

    entities = [
        EntityRef(
            entity_type="errata", entity_id=errata_id, raw_text=f"Errata {errata_id}",
            doc_id=doc_id, resolved=(status == "Verified"),
            extra={"status": status, "type": fields.get("Type", ""), "rfc": rfc_id},
        ),
        EntityRef(
            entity_type="rfc", entity_id=rfc_id, raw_text=rfc_id, doc_id=doc_id, resolved=True,
        ),
    ]
    return ExtractedDoc(
        doc_id=doc_id, source_type="errata", text=text, entities=entities, applies_to=rfc_id,
    )
