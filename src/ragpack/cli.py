"""``ragpack`` command-line interface: ``ragpack ingest <path...>`` and ``ragpack search <query>``."""
from __future__ import annotations

import sys
from typing import Optional

from .pipeline import RAGpack, Settings


def _settings(args) -> Settings:
    return Settings(
        model=args.model,
        device=args.device,
        qdrant=args.qdrant,
        collection=args.collection,
        ocr=args.ocr,
    )


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="ragpack",
        description="Mill documents into a searchable vector store (GPU-optional embeddings + OCR).",
    )
    parser.add_argument("--model", default=Settings().model,
                        help="fastembed model name, or 'hash' for the offline embedder")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--qdrant", default="./ragpack_qdrant",
                        help="':memory:', a local path (default: ./ragpack_qdrant), or an http(s) URL")
    parser.add_argument("--collection", default="ragpack")
    parser.add_argument("--ocr", default="auto", choices=["auto", "never", "always"])

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="index files/folders")
    p_ingest.add_argument("paths", nargs="+", help="files or directories to ingest")
    p_ingest.add_argument("--recreate", action="store_true",
                          help="drop and recreate the collection first")

    p_search = sub.add_parser("search", help="query the index")
    p_search.add_argument("query")
    p_search.add_argument("--top-k", type=int, default=8)

    args = parser.parse_args(argv)
    mill = RAGpack(_settings(args))

    if args.cmd == "ingest":
        n = mill.ingest(
            args.paths,
            recreate=args.recreate,
            on_progress=lambda done, tot: print(f"\r  embedding {done}/{tot}", end="", file=sys.stderr),
        )
        print(f"\nIngested {n} chunks into '{args.collection}' (device={mill.embedder.device}).")
        return 0

    hits = mill.search(args.query, top_k=args.top_k)
    if not hits:
        print("No results.")
        return 0
    for i, hit in enumerate(hits, 1):
        print(f"\n[{i}] score={hit.score:.3f}  {hit.source}")
        print(hit.text[:500].strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
