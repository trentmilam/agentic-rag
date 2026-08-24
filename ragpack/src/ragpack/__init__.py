"""ragpack — mill documents into a searchable vector store.

Extract (text + optional GPU OCR) → chunk → embed (CPU or CUDA) → Qdrant → search.

    from ragpack import RAGpack, Settings
    mill = RAGpack(Settings(qdrant="./data", device="auto"))
    mill.ingest("./docs")
    for hit in mill.search("how does X work?"):
        print(hit.score, hit.source, hit.text[:200])
"""
from .chunk import chunk_text, clean_text
from .embed import DEFAULT_MODEL, Embedder, HashEmbedder
from .evidence import EvidenceVerdict, evaluate_evidence
from .extract import extract_text
from .pipeline import Hit, IngestRetryResult, RAGpack, Settings, ingest, search

__all__ = [
    "RAGpack", "Settings", "Hit", "ingest", "search",
    "Embedder", "HashEmbedder", "DEFAULT_MODEL",
    "extract_text", "chunk_text", "clean_text",
    "EvidenceVerdict", "evaluate_evidence", "IngestRetryResult",
]
__version__ = "0.2.0"
