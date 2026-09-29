"""A real IANA protocol-parameter registry (XML), rendered as markdown tables.

IANA registry XML (``xml.etree.ElementTree``, stdlib) is a ``<registry>`` root that
either holds ``<record>`` elements directly (e.g. ``service-names-port-numbers.xml``,
one flat 14k+-row table) or nests further ``<registry>`` sub-sections, each with its
own title and its own records and often its own DIFFERENT set of columns (e.g.
``dns-parameters.xml`` has 24 sub-registries: "DNS CLASSes", "Resource Record (RR)
TYPEs", etc). :func:`_collect_sections` walks that real structure so each section
gets its own heading + table instead of forcing mismatched columns into one table.

One :class:`EntityRef` per *registry file*, not per row. IANA rows aren't
individually cross-referenced by other source types the way, say, an errata's RFC
number is, so a per-row entity would just be unused volume.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ingest.connectors.base import ExtractedDoc
from ingest.entities import EntityRef


def _rows_to_markdown_table(rows: list[dict], fields: list[str]) -> str:
    """Same technique as the old spreadsheet connector's row-to-table renderer:
    a header row, a separator row, then one pipe-delimited row per record."""
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(row.get(f, "") for f in fields) + " |")
    return "\n".join(lines)


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1]


def _collect_sections(elem: ET.Element, ns: str) -> list[tuple[str, list[dict]]]:
    """Depth-first: a ``<registry>`` with its own ``<record>`` children is one section
    (title + rows); a ``<registry>`` whose children are themselves ``<registry>``
    elements recurses into each instead."""
    sections: list[tuple[str, list[dict]]] = []
    title_el = elem.find(f"{ns}title")
    title = (title_el.text or "").strip() if title_el is not None and title_el.text else elem.get("id", "registry")

    records = elem.findall(f"{ns}record")
    if records:
        rows: list[dict] = []
        for record in records:
            row: dict[str, str] = {}
            for child in record:
                tag = _local_tag(child.tag)
                text = " ".join("".join(child.itertext()).split())
                if not text:
                    continue
                row[tag] = f"{row[tag]}; {text}" if tag in row else text
            rows.append(row)
        sections.append((title, rows))

    for sub_registry in elem.findall(f"{ns}registry"):
        sections.extend(_collect_sections(sub_registry, ns))
    return sections


def extract(path: Path) -> ExtractedDoc:
    root = ET.parse(path).getroot()
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""

    root_title_el = root.find(f"{ns}title")
    doc_title = (root_title_el.text or path.stem).strip() if root_title_el is not None and root_title_el.text else path.stem

    parts = [f"# {doc_title} (IANA registry)"]
    for title, rows in _collect_sections(root, ns):
        if not rows:
            continue
        fields: list[str] = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
        parts.append(f"## {title}\n\n{_rows_to_markdown_table(rows, fields)}")

    text = "\n\n".join(parts)
    doc_id = f"iana_registry/{path.name}"
    entity = EntityRef(
        entity_type="registry", entity_id=path.stem, raw_text=doc_title, doc_id=doc_id, resolved=True,
    )
    return ExtractedDoc(doc_id=doc_id, source_type="iana_registry", text=text, entities=[entity])
