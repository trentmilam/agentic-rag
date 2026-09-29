"""Calibration: measures REAL consilium.router.Router scores against the real
5-module registry (4 retrieval + SupersessionModule) and the real embedder
(BAAI/bge-base-en-v1.5), over one naturally-phrased in-scope query per module
plus one genuinely out-of-scope query. It prints the observed ``ranked``
scores and never invents plausible-sounding ones.

``consilium.router.Router``'s stated library defaults (``floor=0.11``,
``anchor_centroid=0.25``, ``anchor_best_chunk=0.25``) assume a near-zero
baseline cosine between unrelated text: true for a bag-of-words
``HashEmbedder``, not necessarily true for a real dense embedder over a
321k-chunk corpus (the same gap shows up even at a much smaller ~1,100-chunk
scale). This script exists to MEASURE whether that gap is real
here too, rather than assume it. Run it, read the printed numbers, and only
then decide whether ``agenticrag.bootstrap.ROUTER_KWARGS`` needs to depart
from the library defaults.

    python agenticrag/calibrate.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from consilium.router import Router  # noqa: E402

from agenticrag.bootstrap import ROUTER_KWARGS, build_registry  # noqa: E402
from agenticrag.embed_config import get_embedder                # noqa: E402

# One naturally-phrased in-scope query per real source type/capability, plus
# one genuinely out-of-scope query: the exact same set eval_agenticrag.py
# asserts against.
CALIBRATION_QUERIES = [
    ("rfc_text", "How does IP fragmentation and reassembly work in the Internet Protocol?"),
    ("rfc_index", "Who authored RFC 2119 and when was it published?"),
    ("errata", "What errata have been reported against RFC 5322?"),
    ("iana_registry", "What port is registered for HTTPS in the IANA service names registry?"),
    ("supersession", "What obsoleted RFC 2616, the HTTP/1.1 specification?"),
    ("OUT_OF_SCOPE", "What's the best way to season a cast iron skillet before first use?"),
]


def _report(label: str, router: Router) -> None:
    print(f"\n--- {label} ---")
    for expected, question in CALIBRATION_QUERIES:
        rr = router.route(question)
        print(f"\n[{expected}] {question!r}")
        print(f"  abstained={rr.abstained} selected={rr.selected} trace={rr.trace}")
        for name, score, bd in rr.ranked:
            print(f"    {name}: score={score} breakdown={bd}")


def main() -> int:
    t0 = time.time()
    embedder = get_embedder()
    registry = build_registry(embedder)
    print(f"registry built in {time.time() - t0:.1f}s; "
          f"modules={[m.name for m in registry.modules]}")
    for m in registry.modules:
        print(f"  {m.name}: n_chunks={len(m.chunks)}")

    _report("LIBRARY DEFAULTS (floor=0.11, anchor_centroid=0.25, anchor_best_chunk=0.25)",
             Router(registry, embedder))
    _report(f"agentic-rag ROUTER_KWARGS = {ROUTER_KWARGS}",
            Router(registry, embedder, **ROUTER_KWARGS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
