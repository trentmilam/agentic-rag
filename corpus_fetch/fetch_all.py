"""Orchestrates the full real-data fetch: rfc-index -> rfc full text -> rfc_index
cards -> errata -> IANA registries. Run as ``python -m corpus_fetch.fetch_all``.

Deliberately separate from ``ingest/run_ingest.py``: ingest never triggers a network
fetch itself; this step must run first, then ingest reads whatever's already on disk
under ``data/raw/``. Safe to re-run: every step here is independently resumable
(skips files already on disk unless ``--force``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from corpus_fetch.fetch_errata import fetch_errata                        # noqa: E402
from corpus_fetch.fetch_iana import fetch_iana                             # noqa: E402
from corpus_fetch.fetch_rfc_index import fetch_rfc_index, parse_rfc_index  # noqa: E402
from corpus_fetch.fetch_rfc_text import MAX_RFC_NUMBER, fetch_rfc_text     # noqa: E402
from ingest.connectors.rfc_index import render_index_cards                 # noqa: E402


def run(data_dir: Path, *, force: bool = False, max_rfc_number: int = MAX_RFC_NUMBER) -> dict:
    raw_dir = data_dir / "raw"
    cache_dir = raw_dir / "_cache"

    index_path = fetch_rfc_index(cache_dir / "rfc-index.txt", force=force)
    full_index = parse_rfc_index(index_path)
    print(f"[rfc-index] parsed {len(full_index)} issued RFC entries from the live index")

    text_report = fetch_rfc_text(full_index, raw_dir / "rfc_text", max_number=max_rfc_number, force=force)
    print(f"[rfc-text] {json.dumps(text_report['tally'])} (not_issued={text_report['not_issued']})")
    if text_report["failures"]:
        print(f"[rfc-text] {len(text_report['failures'])} failures (see summary.failures below)")

    in_range_numbers = {n for n in full_index if n <= max_rfc_number}
    render_index_cards(full_index, in_range_numbers, raw_dir / "rfc_index")
    print(f"[rfc-index-cards] rendered {len(in_range_numbers)} cards")

    errata_report = fetch_errata(raw_dir / "errata", cache_dir, max_rfc_number=max_rfc_number, force=force)
    print(f"[errata] {errata_report}")

    iana_report = fetch_iana(raw_dir / "iana_registry", force=force)
    print(f"[iana] {iana_report}")

    return {
        "rfc_index_entries_full": len(full_index),
        "rfc_text": text_report,
        "rfc_index_cards": len(in_range_numbers),
        "errata": errata_report,
        "iana": iana_report,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-fetch/re-render even if files already exist")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--max-rfc-number", type=int, default=MAX_RFC_NUMBER)
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve() if args.data_dir else (REPO_ROOT / "data")
    summary = run(data_dir, force=args.force, max_rfc_number=args.max_rfc_number)

    print("\n=== FETCH SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
