# activerag

This is Trenton Milam's own standalone portfolio work.

`activerag` is the Consilium-aware half of a "detect thin evidence, hunt for more, retry
once, audit the result" mechanism. A generic, domain-agnostic version of the same idea
already lives in the sibling repo [RAGpack](https://github.com/trentmilam/RAGpack)
(`ragpack.evidence.evaluate_evidence` / `RAGpack.ingest_and_retry`), which judges a flat
list of raw retrieval hits. `activerag` sits one level higher: it reads the richer
post-integrity-gate signals a [Consilium](https://github.com/trentmilam/consilium) `Answer`
+ `RouteResult` already carry (citations, dropped claims, router margin) and decides whether
that answer is trustworthy enough to ship, or thin enough to warrant hunting for more
evidence -- against the real, 321k-chunk IETF RFC corpus the sibling repo
[agentic-rag](https://github.com/trentmilam/agentic-rag) ingests.

## Sibling repos

`activerag` imports two sibling repos by `sys.path` -- not pip-installed or vendored:

- `activerag/registry_bridge.py` and `refresh_hook.py` reuse
  [agentic-rag](https://github.com/trentmilam/agentic-rag)'s `bootstrap.build_registry`.
  It is resolved lazily -- only when a `RegistryBridge` is constructed without an injected
  `build_registry` -- so importing (or testing) these modules needs no clone at all. To
  drive the real default builder, clone it next to this repo, along with
  [consilium](https://github.com/trentmilam/consilium), which agentic-rag's own bootstrap
  imports from in turn:

  ```
  git clone https://github.com/trentmilam/agentic-rag
  git clone https://github.com/trentmilam/consilium
  ```

- `activerag/headroom_gate.py` reuses the `Headroom` / `GpuProfile` / `Decision` governor
  from [rag-reliability](https://github.com/trentmilam/rag-reliability)'s `headroom` flat
  module. Without it, `activerag/headroom_gate.py` is the one module that will not import;
  the other seven are unaffected:

  ```
  git clone https://github.com/trentmilam/rag-reliability
  ```

`activerag/_paths.py` resolves `../rag-reliability/headroom`, and `registry_bridge.py` adds
`../agentic-rag` to the path itself (lazily, at first default construction).

The tests build every fixture by hand and touch no live service, GPU, or network. 39 of the
54 run with no sibling repo present at all; the 14 in `test_headroom_gate.py` and
`test_orchestrator.py` import the `headroom` governor and skip cleanly when it is absent,
and the one test that resolves the real `agenticrag.bootstrap.build_registry` skips cleanly
when the agentic-rag / consilium clones are absent.

## What's here

- `activerag/evidence.py` -- `evaluate()` / `EvidenceVerdict`: the low-evidence trigger.
  Three independent checks (citation count, dropped-claim ratio, router-floor margin), any
  one of which flags an answer as insufficient; an abstained answer is always insufficient.
- `activerag/priority.py` -- `rank_sources()` / `SourceCandidate`: a cheap, explainable
  (not learned) heuristic for which source to hunt in first, with a `"internet"`
  pseudo-source always sorted last.
- `activerag/telemetry.py` -- `HuntEvent` / `SourceProbeRecord` / `append_event()` /
  `read_events()`: an append-only JSONL audit trail for a hunt cycle. Deliberately has zero
  import dependency on `evidence.py` -- a dumb recorder.
- `activerag/hunt.py` -- `StagingDirHuntSource`: a real `hunt_fn` over one local staging
  directory (one per `source_type`). **Scope, decided deliberately:** staging-directory-only
  -- there is no internet-fetch hunt source here; that stays a separate follow-up.
- `activerag/headroom_gate.py` -- `HuntHeadroomGate` / `evaluate_simulated()`: a thin
  adapter over the REAL `Headroom` / `GpuProfile` / `Decision` governor from the sibling
  repo `rag-reliability` (`headroom/headroom.py`), reused wholesale, not reimplemented.
  Only the fed telemetry is simulated (clearly labelled `SIM_HEALTHY_ROOMY` /
  `SIM_NEAR_WEDGE_TIGHT`) -- there is no `nvidia-smi`/`pynvml` call anywhere in this repo.
- `activerag/registry_bridge.py` -- `RegistryBridge`: holds one live agentic-rag
  `consilium.registry.Registry` and knows how to rebuild + wholesale-swap it
  (`refresh_all()`), reusing agentic-rag's own `bootstrap.build_registry` as the injected
  builder. Verified against the real 321,124-chunk Qdrant collection: construction and a
  second `refresh_all()` each really rebuild the registry, producing a genuinely new object
  each time, not a mutation. This is the exact same `build_registry()` cost agentic-rag's own
  README documents -- a scan for the small poison-quarantine set via
  `agenticrag/qdrant_retrieval.py::load_salient_chunks_by_source` -- **not**
  `agenticrag/registry_loader.py::load_module_from_qdrant`'s much costlier full-module
  scroll (that function is only used by `eval/prove_revision_guard.py`; this bridge never
  calls it). Measured (CPU-only, no CUDA execution provider; 3 consecutive `build_registry()`
  calls, not isolated from background load): **~35s/build** when the bridge is constructed
  with an explicit shared `client=` kwarg (the client stays open, so a rebuild skips
  re-opening the on-disk store); **~78-104s/build** when no client is passed (plain
  `RegistryBridge(embedder)`), because every `build_registry()` call then opens its own fresh
  `QdrantClient`. The no-client mode also has a sharp edge worth knowing before relying on it:
  local-mode Qdrant allows only one opener per folder and `build_registry` never closes a
  client it opened on success, so calling `refresh_all()` a second time on a bridge built
  *without* a shared client raises `RuntimeError: Storage folder ... already accessed by
  another instance` -- pass `client=get_qdrant_client()` explicitly if a process needs more
  than one rebuild.
- `activerag/orchestrator.py` -- `run_hunt_cycle()` / `OrchestrationResult`: the conductor.
  Evaluates existing evidence; if sufficient, short-circuits (no ranking, no hunt, no
  telemetry). Otherwise ranks candidate sources and tries each in priority order, bounded
  (stops at the first hunt that resolves the verdict, or when candidates are exhausted),
  gated by `headroom_gate` before every attempt, with every attempt recorded via
  `telemetry.append_event()`. Deliberately generalizes RAGpack's "single hunt, never twice"
  contract into "try multiple source-typed hunts in priority order within one bounded
  cycle" -- a documented design decision, not a silent contract violation; the bound itself
  (each candidate tried at most once) is non-negotiable.
- `activerag/refresh_hook.py` -- `make_refresh_and_research()`: the REAL implementation of
  the `refresh_and_research` callable `orchestrator.run_hunt_cycle` only takes as an
  injected dependency. Copies newly-hunted files into agentic-rag's own
  `data/raw/<source_type>/`, re-runs agentic-rag's real `ingest.run_ingest.run()` (only
  re-embeds changed files), rebuilds the registry via `RegistryBridge.refresh_all()`, then
  re-answers the query through `consilium.router.Router.route()` +
  `consilium.composer.compose(..., harden=True)` (not `answer_v3`'s summarized dict --
  `evidence.evaluate()` needs the raw `Answer`/`RouteResult` objects) and re-evaluates the
  evidence. Each of the four real primitives it drives (ingest, registry rebuild, route+
  compose, evidence evaluation) is independently proven elsewhere in this cluster; this
  module's own tests (`tests/test_refresh_hook.py`) prove only its call order and data flow,
  against injected fakes for each primitive -- the same dependency-injection idiom
  `RegistryBridge`/`orchestrator` already use.

Every module above is independently unit-tested against hand-built fixture objects; none
of the 54 tests in this repo touch a live Consilium instance, embedder, or real corpus --
that boundary is deliberate (see `activerag/registry_bridge.py`'s and `refresh_hook.py`'s
own docstrings for what was additionally verified live, outside the committed test suite).

## What's explicitly NOT here

- A live internet-fetch hunt source (`hunt.py` stays staging-directory-only -- see above).
- A full, single, real end-to-end run of the whole chain (real hunt -> real ingest -> real
  reingest -> real re-answer) in one shot: the already-ingested corpus has nothing left
  un-ingested to hunt for without fabricating a document, so this is proven by composition
  of independently-verified real calls instead. A natural follow-up if a genuinely new,
  previously-unseen document is ever available.

## Running the tests

```
pip install -e .[dev]
pytest
```

No external services, no GPU, no network -- every test constructs its fixtures by hand.
`activerag/headroom_gate.py` needs `numpy` (see `pyproject.toml`) -- it is a real,
transitive dependency of the sibling `rag-reliability/headroom` module it imports by
`sys.path`, not something this repo vendors or reimplements.
