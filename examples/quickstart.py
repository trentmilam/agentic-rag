"""Minimal ragpack example — fully offline (HashEmbedder + in-memory Qdrant, no downloads).

    python examples/quickstart.py
"""
from __future__ import annotations

import pathlib
import tempfile

from ragpack import RAGpack, Settings


def main() -> None:
    docs = pathlib.Path(tempfile.mkdtemp())
    (docs / "backoff.md").write_text(
        "Retry logic uses exponential backoff with jitter to avoid thundering herds.",
        encoding="utf-8",
    )
    (docs / "billing.md").write_text(
        "The billing module computes invoices monthly and emails a PDF receipt.",
        encoding="utf-8",
    )

    # model="hash" = deterministic offline embedder; swap to Settings(device="auto") for a real model.
    mill = RAGpack(Settings(model="hash", qdrant=":memory:"))
    print(f"ingested {mill.ingest(docs)} chunks (device={mill.embedder.device})")

    for hit in mill.search("how does retry work?", top_k=2):
        print(f"  {hit.score:.3f}  {hit.source}: {hit.text}")


if __name__ == "__main__":
    main()
