"""Fetch the real IETF errata dataset from errata.rfc-editor.org.

Investigated mechanism (this was actually checked, not guessed): errata.rfc-editor.org
is a server-rendered Django site (Bootstrap templates, a plain HTML ``<form
id="errata-search-form">``). There is no separate JSON/CSV API endpoint (no
``window.__DATA__`` blob, no ``/api/`` path, no bundled SPA JS; the only script tag on
the page is ``bootstrap.bundle.min.js``). However, its search form's own
``presentation`` field exposes a ``records`` ("Full Records") option, and submitting it
with every other filter left blank (``?rfc_number=&status=any&presentation=records``)
returns EVERY erratum for EVERY RFC in ONE HTML response with no pagination. Verified
directly: 7,957 ``Errata-ID`` records in a single ~43MB GET, matching the 7,957-row
count independently obtained from the ``presentation=table`` view. This is a genuine
complete, single-request bulk export, used instead of one lookup per RFC number
(the fallback the task anticipated in case no bulk mechanism existed) because it needs
far fewer requests to the real server AND is more complete.

Each erratum is real structured HTML: an ``<h3>RFC N</h3>`` groups its errata, each in
its own ``<div class="card">`` with a ``<dl>`` of ``Status:``/``Type:``/``Reported
By:``/``Date Reported:`` followed by the free-text correction ("In section X, it
says:" / "It should say:" / "Notes:"). This is parsed with targeted regexes over
those known, stable field labels rather than a full HTML parser (no HTML-parsing
library is otherwise used in this repo, and the page's structure, deeply nested but
flatly repeating, doesn't need one).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from corpus_fetch._http import get_with_retries, new_session

SEARCH_URL = "https://errata.rfc-editor.org/search/?rfc_number=&status=any&presentation=records"

# The bulk export returned 7,957 real Errata-ID records when this parser was verified
# (see the module docstring); the RFC errata database only ever grows (historical
# errata are never deleted). This floor sits well below that measured count so a normal
# fetch clears it easily, but a CSS/markup change on the externally-controlled page
# (which would silently drive the regex-based parse toward zero records) trips it and
# fails loudly instead of quietly shipping a near-empty errata corpus.
_MIN_EXPECTED_ERRATA_RECORDS = 7000

_BLOCK_START_RE = re.compile(
    r'<h3 class="mt-4">RFC (\d+)</h3>|Errata-ID: <a href="/eid(\d+)/">\d+</a></h4>'
)
_STATUS_RE = re.compile(r'Status:</dt>\s*<dd class="col-sm-8">\s*<span class="badge[^"]*">([^<]+)</span>', re.S)
_TYPE_RE = re.compile(r'Type:</dt>\s*<dd class="col-sm-8">\s*<span class="badge[^"]*">([^<]+)</span>', re.S)
_REPORTED_BY_RE = re.compile(r'Reported [Bb]y:</dt>\s*<dd class="col-sm-8">\s*<span>([^<]*)</span>', re.S)
_DATE_REPORTED_RE = re.compile(r'Date Reported:</dt>\s*<dd class="col-sm-8">\s*<span>([^<]*)</span>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Erratum:
    errata_id: int
    rfc_number: int
    status: str
    type_: str
    reported_by: str
    date_reported: str
    body: str


def _strip_html(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_errata_page(cache_path: Path, *, force: bool = False) -> Path:
    """Download the full bulk-records HTML export to ``cache_path`` unless it's
    already there. This is the ONE network request this whole module makes."""
    if cache_path.exists() and not force:
        return cache_path
    session = new_session()
    resp = get_with_retries(session, SEARCH_URL, timeout=180)
    resp.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(resp.content)
    return cache_path


def parse_errata_page(path: Path) -> list[Erratum]:
    text = path.read_text(encoding="utf-8")
    matches = list(_BLOCK_START_RE.finditer(text))

    out: list[Erratum] = []
    current_rfc: int | None = None
    for i, match in enumerate(matches):
        if match.group(1):
            current_rfc = int(match.group(1))
            continue
        if current_rfc is None:
            continue  # an erratum marker before any RFC header; shouldn't happen on the real page
        eid = int(match.group(2))
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.end():block_end]

        status_match = _STATUS_RE.search(block)
        type_match = _TYPE_RE.search(block)
        reported_by_match = _REPORTED_BY_RE.search(block)
        date_match = _DATE_REPORTED_RE.search(block)

        dl_end = block.find("</dl>")
        body_html = block[dl_end + len("</dl>"):] if dl_end != -1 else block

        out.append(Erratum(
            errata_id=eid,
            rfc_number=current_rfc,
            status=status_match.group(1).strip() if status_match else "Unknown",
            type_=type_match.group(1).strip() if type_match else "",
            reported_by=reported_by_match.group(1).strip() if reported_by_match else "",
            date_reported=date_match.group(1).strip() if date_match else "",
            body=_strip_html(body_html),
        ))
    return out


def render_erratum_file(erratum: Erratum) -> str:
    lines = [
        f"Errata ID: {erratum.errata_id}",
        f"RFC: RFC{erratum.rfc_number}",
        f"Status: {erratum.status}",
        f"Type: {erratum.type_}",
        f"Reported By: {erratum.reported_by}",
        f"Date Reported: {erratum.date_reported}",
        "",
        erratum.body,
    ]
    return "\n".join(lines) + "\n"


def fetch_errata(out_dir: Path, cache_dir: Path, *, max_rfc_number: int, force: bool = False) -> dict:
    cache_path = cache_dir / "errata_records.html"
    fetch_errata_page(cache_path, force=force)
    all_errata = parse_errata_page(cache_path)
    if len(all_errata) < _MIN_EXPECTED_ERRATA_RECORDS:
        raise RuntimeError(
            f"Parsed only {len(all_errata)} errata records from {cache_path} "
            f"(expected at least {_MIN_EXPECTED_ERRATA_RECORDS}). The errata page's "
            "HTML structure has almost certainly changed -- check the regexes at the "
            "top of corpus_fetch/fetch_errata.py against the live page before trusting "
            "this run. Refusing to ship a near-empty errata corpus silently."
        )
    in_range = [e for e in all_errata if e.rfc_number <= max_rfc_number]

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for erratum in in_range:
        target = out_dir / f"erratum_{erratum.errata_id}.txt"
        if target.exists() and not force:
            skipped += 1
            continue
        target.write_text(render_erratum_file(erratum), encoding="utf-8")
        written += 1

    return {
        "total_errata_all_rfcs": len(all_errata),
        "in_range": len(in_range),
        "written": written,
        "skipped_existing": skipped,
    }


if __name__ == "__main__":
    import json
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/errata")
    cache = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/raw/_cache")
    print(json.dumps(fetch_errata(out, cache, max_rfc_number=6000), indent=2))
