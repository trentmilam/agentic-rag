"""Fetch + parse the real IETF RFC master index.

``https://www.rfc-editor.org/rfc-index.txt`` is the authoritative, plain-text listing
of every RFC ever issued (9,000+ entries as of this writing), including the real
``(Obsoletes NNNN)`` / ``(Obsoleted by NNNN)`` / ``(Updates NNNN)`` / ``(Updated by
NNNN)`` relationship tags -- a genuine many-to-many directed supersession graph, not a
fabricated linear revision history. It is cached once to disk (it changes rarely and
is ~2MB); every other fetcher and ``ingest/run_ingest.py`` re-parses the cached copy
locally instead of re-downloading it.

Parsing approach (verified against the live index, not guessed): each entry starts at
column 0 with a bare RFC number; continuation lines are indented. Entries are
reassembled by joining their lines with spaces, then parsed with regexes anchored on
the index's own fixed vocabulary (``(Format:``, ``(Status:``, etc). The one genuinely
ambiguous step is splitting "Title. Authors. Date." into title vs. authors, since
titles can themselves contain periods and author lists are just comma-separated prose
too -- see :func:`_split_title_authors` for the (measured) heuristic used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from corpus_fetch._http import get_with_retries, new_session

INDEX_URL = "https://www.rfc-editor.org/rfc-index.txt"

_ENTRY_START_RE = re.compile(r"^\d+\s")
_NUMBER_RE = re.compile(r"^(\d+)\s+(.*)$")
_DATE_RE = re.compile(r"\s((?:\d{1,2}\s+)?[A-Z][a-z]+\.?\s+\d{4})\.\s*\(Format:")
_STATUS_RE = re.compile(r"\(Status:\s*([^)]+)\)")
_OBSOLETES_RE = re.compile(r"\(Obsoletes\s+([^)]+)\)")
_OBSOLETED_BY_RE = re.compile(r"\(Obsoleted by\s+([^)]+)\)")
_UPDATES_RE = re.compile(r"\(Updates\s+([^)]+)\)")
_UPDATED_BY_RE = re.compile(r"\(Updated by\s+([^)]+)\)")

# A real author name token: one or more single-letter "X." initials followed by a
# capitalized surname, with an optional generational/editor suffix. The initials are
# deliberately restricted to a single letter (not "[A-Za-z]*\." -- which would also
# match an ordinary title word like "Software.") -- real RFC-index author initials are
# always this short; title words that happen to end a sentence are not. Matched
# against the *live* 9,794-entry issued-RFC index, a left-to-right scan for the first
# position where the remainder of the "title + authors" string matches this grammar
# all the way to the end finds the true author-list boundary for 9,509 of them (97.1%).
_NAME_TOKEN = r"[A-Z]\.(?:\s?[A-Z]\.)*\s+[A-Z][A-Za-z'\-]+(?:\s+(?:Jr\.|Sr\.|II|III|IV))?"
_AUTHOR_TAIL_RE = re.compile(
    r"^(" + _NAME_TOKEN + r"(?:,\s*Eds?\.)?(?:,\s*" + _NAME_TOKEN + r"(?:,\s*Eds?\.)?)*)\.$"
)


@dataclass
class RfcIndexEntry:
    number: int
    title: str
    authors: str
    date: str
    status: str
    obsoletes: list[int] = field(default_factory=list)
    obsoleted_by: list[int] = field(default_factory=list)
    updates: list[int] = field(default_factory=list)
    updated_by: list[int] = field(default_factory=list)


def fetch_rfc_index(cache_path: Path, *, force: bool = False) -> Path:
    """Download rfc-index.txt to ``cache_path`` unless it's already there."""
    if cache_path.exists() and not force:
        return cache_path
    session = new_session()
    resp = get_with_retries(session, INDEX_URL, timeout=60)
    resp.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(resp.content)
    return cache_path


def _ints(group: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", group)]


def _split_title_authors(title_and_authors: str) -> tuple[str, str]:
    """Locate the real author-list tail of a "Title. Authors." string.

    The ~2.8% of real entries that don't match the name-token grammar are almost all
    pre-1980 RFCs "authored" by an institution (e.g. "National Bureau of Standards.")
    with no initials to anchor on; for those we fall back to splitting on the last
    ". " run, which is still a real, reasonable split even though it isn't verified by
    the name grammar.
    """
    for start in range(len(title_and_authors)):
        candidate = title_and_authors[start:]
        match = _AUTHOR_TAIL_RE.match(candidate)
        if match:
            title = title_and_authors[:start].strip()
            if title.endswith("."):
                title = title[:-1]
            return title, match.group(1).strip()
    if ". " in title_and_authors:
        title, _, authors = title_and_authors.rpartition(". ")
        return title.strip(), authors.strip()
    return title_and_authors.strip(), ""


def _parse_entry(joined_lines: str) -> RfcIndexEntry | None:
    entry_text = re.sub(r"\s+", " ", joined_lines).strip()
    num_match = _NUMBER_RE.match(entry_text)
    if not num_match:
        return None
    number = int(num_match.group(1))
    if num_match.group(2).strip().startswith("Not Issued"):
        return None

    date_match = _DATE_RE.search(entry_text)
    if not date_match:
        # Every real issued entry carries a "(Format:" tag with a preceding date
        # (verified against the live index: 0 issued entries lack one) -- if this
        # ever fires it means the index's own format changed, not a value to guess at.
        raise ValueError(f"RFC {number}: could not locate a date/(Format: tag -- {entry_text[:200]!r}")
    date = date_match.group(1).strip()
    title_and_authors = entry_text[num_match.end(1):date_match.start()].strip()
    title, authors = _split_title_authors(title_and_authors)

    status_match = _STATUS_RE.search(entry_text)
    if not status_match:
        raise ValueError(f"RFC {number}: no (Status: tag found -- {entry_text[:200]!r}")
    status = status_match.group(1).strip()

    obsoletes_match = _OBSOLETES_RE.search(entry_text)
    obsoleted_by_match = _OBSOLETED_BY_RE.search(entry_text)
    updates_match = _UPDATES_RE.search(entry_text)
    updated_by_match = _UPDATED_BY_RE.search(entry_text)

    return RfcIndexEntry(
        number=number,
        title=title,
        authors=authors,
        date=date,
        status=status,
        obsoletes=_ints(obsoletes_match.group(1)) if obsoletes_match else [],
        obsoleted_by=_ints(obsoleted_by_match.group(1)) if obsoleted_by_match else [],
        updates=_ints(updates_match.group(1)) if updates_match else [],
        updated_by=_ints(updated_by_match.group(1)) if updated_by_match else [],
    )


def parse_rfc_index(path: Path) -> dict[int, RfcIndexEntry]:
    """Parse every entry (including ``Not Issued`` gaps, which are dropped) in the
    cached rfc-index.txt into ``{number: RfcIndexEntry}``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: dict[int, RfcIndexEntry] = {}
    current_lines: list[str] = []
    started = False

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            entry = _parse_entry(" ".join(current_lines))
            if entry is not None:
                entries[entry.number] = entry
        current_lines = []

    for line in text.splitlines():
        if _ENTRY_START_RE.match(line):
            flush()
            current_lines = [line.strip()]
            started = True
        elif started and line.strip():
            current_lines.append(line.strip())
    flush()
    return entries


if __name__ == "__main__":
    import sys

    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/_cache/rfc-index.txt")
    fetch_rfc_index(cache)
    idx = parse_rfc_index(cache)
    print(f"parsed {len(idx)} issued RFC entries from {cache}")
