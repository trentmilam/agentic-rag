"""RFC full text, ingested verbatim.

Each ``rfcNNNN.txt`` under ``data/raw/rfc_text/`` is the exact, unmodified body
fetched from ``https://www.rfc-editor.org/rfc/rfcNNNN.txt``, including its own
IETF Trust copyright notice, which is never stripped (the Trust Legal Provisions that
permit republishing this text at all require it to stay intact).

``part_number`` holds ``f"RFC{number}"``, the lookup key ``run_ingest.py`` uses
against the real Obsoletes/Obsoleted-by graph to decide ``is_current``; this connector
has no revision concept of its own to set ``revision`` to (an RFC's full text is a
single immutable document, never a specific revision of a series).
"""
from __future__ import annotations

import re
from pathlib import Path

from ingest.connectors.base import ExtractedDoc
from ingest.entities import EntityRef

_FILENAME_RE = re.compile(r"^rfc(\d+)\.txt$")


def extract(path: Path) -> ExtractedDoc:
    match = _FILENAME_RE.match(path.name)
    if match is None:
        raise ValueError(f"{path}: filename does not match 'rfcNNNN.txt'")
    number = int(match.group(1))
    text = path.read_text(encoding="utf-8", errors="replace")
    doc_id = f"rfc_text/{path.name}"

    entity = EntityRef(
        entity_type="rfc", entity_id=f"RFC{number}", raw_text=f"RFC {number}",
        doc_id=doc_id, resolved=True,
    )
    return ExtractedDoc(
        doc_id=doc_id, source_type="rfc_text", text=text, entities=[entity],
        part_number=f"RFC{number}",
    )
