"""Fetch RFC full text, verbatim and unmodified, for RFC 1 through 6000.

A clean, deterministic, reproducible range (skipping numbers the real index marks
``Not Issued`` -- no document exists for those). Each ``rfcNNNN.txt`` is fetched from
the confirmed-working pattern ``https://www.rfc-editor.org/rfc/rfcNNNN.txt`` and
written to disk byte-for-byte, including the RFC's own embedded IETF Trust copyright
notice. Resumable: an existing file is left alone unless ``force=True``.

Measured throughput (this environment, 8 concurrent connections): ~50 requests/sec
against rfc-editor.org, so the full ~5,800-request range (6000 minus ``Not Issued``
gaps) takes on the order of a couple of minutes, not hours.
"""
from __future__ import annotations

import json
from pathlib import Path

from corpus_fetch._http import DEFAULT_MAX_WORKERS, fetch_many, get_with_retries, new_session
from corpus_fetch.fetch_rfc_index import RfcIndexEntry

TEXT_URL_TEMPLATE = "https://www.rfc-editor.org/rfc/rfc{number}.txt"
MAX_RFC_NUMBER = 6000


def fetch_rfc_text(
    index: dict[int, RfcIndexEntry], out_dir: Path, *,
    max_number: int = MAX_RFC_NUMBER, force: bool = False, max_workers: int = DEFAULT_MAX_WORKERS,
) -> dict:
    """Fetch full text for every issued RFC number in ``[1, max_number]`` per the real
    parsed index (``Not Issued`` numbers -- absent from ``index`` -- are skipped, not
    guessed at). Every outcome (fetched / skipped-existing / not-found / error) is
    tallied and returned; nothing is silently swallowed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    numbers = [n for n in range(1, max_number + 1) if n in index]
    not_issued = max_number - len(numbers)

    session = new_session()
    results: dict[int, str] = {}
    failures: list[tuple[int, str]] = []

    def worker(number: int) -> None:
        target = out_dir / f"rfc{number}.txt"
        if target.exists() and not force:
            results[number] = "skipped_existing"
            return
        try:
            resp = get_with_retries(session, TEXT_URL_TEMPLATE.format(number=number))
            if resp.status_code == 404:
                results[number] = "not_found"
                failures.append((number, "404 not found"))
                return
            resp.raise_for_status()
            target.write_bytes(resp.content)
            results[number] = "fetched"
        except Exception as exc:  # noqa: BLE001 -- one bad RFC must not abort the whole batch
            results[number] = "error"
            failures.append((number, f"{type(exc).__name__}: {exc}"))

    fetch_many(numbers, worker, max_workers=max_workers)

    tally: dict[str, int] = {}
    for status in results.values():
        tally[status] = tally.get(status, 0) + 1

    return {
        "requested_range": max_number,
        "not_issued": not_issued,
        "attempted": len(numbers),
        "tally": tally,
        "failures": failures,
    }


if __name__ == "__main__":
    import sys

    from corpus_fetch.fetch_rfc_index import fetch_rfc_index, parse_rfc_index

    cache = Path("data/raw/_cache/rfc-index.txt")
    fetch_rfc_index(cache)
    full_index = parse_rfc_index(cache)
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/rfc_text")
    report = fetch_rfc_text(full_index, out_dir)
    print(json.dumps(report, indent=2))
