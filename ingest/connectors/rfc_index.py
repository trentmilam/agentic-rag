"""Per-RFC "index card" documents rendered from the real parsed rfc-index.txt.

``rfc-index.txt`` is one giant file covering every RFC ever issued, but for
retrieval we want one small, independently-chunkable document per RFC, so
:func:`render_index_cards` (called once from the fetch pipeline, not at query time)
writes one real-facts-only card per RFC number in the text-fetch range, and
``extract()`` reads a card back into an :class:`ExtractedDoc`.

Cards use a fixed line-per-field layout (``Label: value``) rather than the flowing
sentence style rfc-index.txt itself uses: real author lists and titles both contain
periods, so a flowing sentence can't be round-tripped unambiguously once *we* are also
the reader; a labeled line always can.

:func:`build_revisions_index` is the other real, authoritative artifact this module
owns: the full Obsoletes/Obsoleted-by/Updates/Updated-by graph for *every* RFC in the
live index (not just the text-fetch subset), because a supersession chain can walk
outside that subset even when the chunk-level currency check (``run_ingest.py``) only
ever needs entries within it.
"""
from __future__ import annotations

import re
from pathlib import Path

from corpus_fetch.fetch_rfc_index import RfcIndexEntry
from ingest.connectors.base import ExtractedDoc
from ingest.entities import EntityRef

_HEADER_RE = re.compile(r"^RFC (\d+) -- (.*)$")


def _render_card(entry: RfcIndexEntry) -> str:
    lines = [
        f"RFC {entry.number} -- {entry.title}",
        f"Authors: {entry.authors}",
        f"Date: {entry.date}",
        f"Status: {entry.status}",
    ]
    if entry.obsoletes:
        lines.append("Obsoletes: " + ", ".join(f"RFC {n}" for n in entry.obsoletes))
    if entry.obsoleted_by:
        lines.append("Obsoleted by: " + ", ".join(f"RFC {n}" for n in entry.obsoleted_by))
    if entry.updates:
        lines.append("Updates: " + ", ".join(f"RFC {n}" for n in entry.updates))
    if entry.updated_by:
        lines.append("Updated by: " + ", ".join(f"RFC {n}" for n in entry.updated_by))
    return "\n".join(lines) + "\n"


def render_index_cards(index: dict[int, RfcIndexEntry], rfc_numbers: set[int], out_dir: Path) -> None:
    """Write one ``rfcNNNN.txt`` card per number in ``rfc_numbers`` that has a real
    entry in ``index``. Silently skips numbers with no entry (e.g. a number outside
    the live index's current range); it does not fabricate one."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for number in sorted(rfc_numbers):
        entry = index.get(number)
        if entry is None:
            continue
        (out_dir / f"rfc{number}.txt").write_text(_render_card(entry), encoding="utf-8")


def _parse_id_list(fields: dict[str, str], label: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", fields.get(label, ""))]


def extract(path: Path) -> ExtractedDoc:
    text = path.read_text(encoding="utf-8")
    doc_id = f"rfc_index/{path.name}"
    lines = text.splitlines()
    if not lines:
        raise ValueError(f"{path}: empty index card")
    header = _HEADER_RE.match(lines[0])
    if header is None:
        raise ValueError(f"{path}: missing 'RFC NNNN -- Title' header line")
    number = int(header.group(1))

    fields: dict[str, str] = {}
    for line in lines[1:]:
        label, sep, value = line.partition(": ")
        if sep:
            fields[label.strip()] = value.strip()

    entity = EntityRef(
        entity_type="rfc",
        entity_id=f"RFC{number}",
        raw_text=f"RFC {number}",
        doc_id=doc_id,
        resolved=True,
        extra={
            "obsoletes": _parse_id_list(fields, "Obsoletes"),
            "obsoleted_by": _parse_id_list(fields, "Obsoleted by"),
            "updates": _parse_id_list(fields, "Updates"),
            "updated_by": _parse_id_list(fields, "Updated by"),
            "status": fields.get("Status", ""),
        },
    )
    return ExtractedDoc(
        doc_id=doc_id, source_type="rfc_index", text=text, entities=[entity],
        part_number=f"RFC{number}",
    )


def build_revisions_index(full_index: dict[int, RfcIndexEntry]) -> dict:
    """The authoritative ``{"RFCn": {...}}`` supersession graph over *every* RFC in the
    live index. ``run_ingest.py``'s currency check looks entries up here by
    ``doc.part_number``."""
    return {
        f"RFC{number}": {
            "obsoletes": entry.obsoletes,
            "obsoleted_by": entry.obsoleted_by,
            "updates": entry.updates,
            "updated_by": entry.updated_by,
            "status": entry.status,
            "title": entry.title,
        }
        for number, entry in full_index.items()
    }
