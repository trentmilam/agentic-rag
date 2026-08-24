"""make_refresh_and_research: the REAL, live implementation of the
``refresh_and_research`` hook :mod:`activerag.orchestrator` only takes as an
injected callable (the orchestrator owns control flow only and leaves the live
embedder/Qdrant/registry wiring to this closure -- see its "Injection point for
the real registry" docstring section).

Given a query, the source type just hunted, and the freshly-hunted document
paths, the real hook:

1. **Places the hunted files** where agentic-rag's own ingest pipeline expects
   them -- copied into ``<agentic-rag>/data/raw/<source_type>/`` under their
   own filename. This repo never invents a parallel ingest path: it reuses
   ``ingest.run_ingest.run()`` verbatim, the exact same batch ingest agentic-rag's
   own corpus fetch uses, which only re-embeds files whose content hash changed
   (``ingest/state.py``) -- so re-running it after one new file lands is cheap
   relative to a from-scratch ingest. A hunted file must already be named to
   match its source type's connector (e.g. ``rfcNNNN.txt`` for ``rfc_text`` --
   see ``ingest/connectors/rfc_text.py``); if it isn't, ``connector.extract()``
   raises, and that is the correct, honest failure -- this hook does not
   silently rename or reshape a hunted document to fit.
2. **Refreshes the registry** via the injected :class:`~activerag.registry_bridge.
   RegistryBridge` (already covers "rebuild + wholesale swap" -- reused, not
   re-implemented).
3. **Re-answers the query** through the same real primitives
   ``consilium.compute.answer_v3`` uses internally for its text path --
   ``Router.route()`` then ``composer.compose(..., harden=True)`` -- rather
   than through ``answer_v3`` itself, because :func:`activerag.evidence.evaluate`
   needs the raw ``Answer``/``RouteResult`` objects (``.citations``, ``.dropped``,
   ``.trace``), not ``answer_v3``'s already-summarized dict (whose ``"citations"``
   key is a count, not a list).
4. **Re-evaluates the evidence** via :func:`activerag.evidence.evaluate` and
   returns the resulting :class:`~activerag.evidence.EvidenceVerdict`.

Each of these four steps is an already-independently-tested real primitive
(agentic-rag's own ingest tests, a live ``RegistryBridge`` smoke test, the
full ``eval_agenticrag.py`` PASS, and ``evidence.py``'s own fixture suite). Matching this codebase's own established idiom (``RegistryBridge``
injects ``build_registry``; ``orchestrator`` injects ``gate``/``hunt_sources``/
``refresh_and_research`` itself), the four real callables this glue drives are
themselves injectable constructor parameters, defaulting to the real ones --
so :func:`test_refresh_hook.py` can prove call order and data flow against
fakes, hermetically, without re-proving what each primitive already proved for
real elsewhere. A full live chain (real hunt -> real ingest -> real reingest ->
real re-answer, all in one run) is a natural follow-up if a genuinely new,
previously-unseen document is ever available to hunt with; the corpus already
ingested has nothing left un-ingested to manufacture that case honestly.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Sequence

from activerag._paths import REPO_ROOT, add_sibling_paths

add_sibling_paths()

from activerag.evidence import EvidenceVerdict, evaluate as evaluate_evidence  # noqa: E402
from activerag.registry_bridge import RegistryBridge  # noqa: E402

# The repo root itself. This was ``PROJECTS_ROOT / "agentic-rag"`` back when agentic-rag
# was the checkout next door; after the merge that expression still resolved -- but only
# because the working copy happens to be named agentic-rag. Cloned under any other
# directory name it would have pointed at nothing, and ``mkdir(parents=True)`` below
# would have created that nothing rather than failing.
_AGENTIC_RAG_ROOT = Path(REPO_ROOT)


def _real_run_ingest(data_dir: Path) -> None:
    from ingest import run_ingest

    run_ingest.run(data_dir=data_dir)


def _real_route_and_compose(query: str, registry, embedder, router_kwargs: dict):
    from consilium.composer import compose
    from consilium.router import Router

    router = Router(registry, embedder, **router_kwargs)
    route_result = router.route(query)
    answer = compose(query, route_result, registry, embedder, harden=True)
    return answer, route_result


def make_refresh_and_research(
    bridge: RegistryBridge,
    embedder,
    router_kwargs: dict,
    *,
    agentic_rag_root: Path = _AGENTIC_RAG_ROOT,
    run_ingest_fn: Callable[[Path], None] = _real_run_ingest,
    route_and_compose_fn: Callable = _real_route_and_compose,
) -> Callable[[str, str, Sequence[Path]], EvidenceVerdict]:
    """Build the real ``refresh_and_research`` closure ``orchestrator.run_hunt_cycle``
    injects. ``embedder``/``router_kwargs`` are passed explicitly (not read off
    ``bridge``) so this module never needs a private accessor into
    :class:`RegistryBridge` beyond its public ``.registry``. ``run_ingest_fn``/
    ``route_and_compose_fn`` default to the real primitives; tests inject fakes."""

    def refresh_and_research(query: str, source_type: str, found_docs: Sequence[Path]) -> EvidenceVerdict:
        raw_dir = agentic_rag_root / "data" / "raw" / source_type
        raw_dir.mkdir(parents=True, exist_ok=True)
        for doc in found_docs:
            doc = Path(doc)
            shutil.copy2(doc, raw_dir / doc.name)

        run_ingest_fn(agentic_rag_root / "data")
        registry = bridge.refresh_all()
        answer, route_result = route_and_compose_fn(query, registry, embedder, router_kwargs)
        return evaluate_evidence(answer, route_result)

    return refresh_and_research
