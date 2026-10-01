# activerag

Evidence check and retry for Consilium answers. Part of the agentic-rag monorepo.

- Reads the citations, dropped claims and router margin on a [`consilium`](../consilium) `Answer` + `RouteResult`.
- Flags thin evidence, hunts for more, retries once, audits the result.
- Runs against the ~321k-chunk IETF RFC corpus.
- Generic version: [`ragpack`](../ragpack) (`ragpack.evidence.evaluate_evidence`, `RAGpack.ingest_and_retry`).

## Dependencies

After the repo root `pip install -e .`, `import ragpack`, `import consilium` and `from agenticrag.bootstrap import build_registry` resolve.

External: [rag-reliability](https://github.com/trentmilam/rag-reliability), for the `Headroom` / `GpuProfile` / `Decision` governor used by `activerag/headroom_gate.py`.

```
git clone https://github.com/trentmilam/rag-reliability
```

- Clone it as a sibling of the agentic-rag repo.
- Resolved by path (`activerag/_paths.py`), not pip-installed.
- Without it, `headroom_gate.py` does not import. The other seven modules are unaffected.

## Modules

- `evidence.py`: `evaluate()` / `EvidenceVerdict`. Three checks: citation count, dropped-claim ratio, router-floor margin. Any one flags the answer as insufficient. An abstained answer is always insufficient.
- `priority.py`: `rank_sources()` / `SourceCandidate`. Heuristic source ranking, not learned. `"internet"` pseudo-source sorts last.
- `telemetry.py`: `HuntEvent` / `SourceProbeRecord` / `append_event()` / `read_events()`. Append-only JSONL audit trail.
- `hunt.py`: `StagingDirHuntSource`. Hunts one local staging directory per `source_type`. No internet fetch.
- `headroom_gate.py`: `HuntHeadroomGate` / `evaluate_simulated()`. Adapter over the `rag-reliability` governor. Telemetry is simulated (`SIM_HEALTHY_ROOMY` / `SIM_NEAR_WEDGE_TIGHT`). No `nvidia-smi` or `pynvml` calls.
- `registry_bridge.py`: `RegistryBridge`. Holds one live `consilium.registry.Registry`. `refresh_all()` rebuilds and swaps it using `bootstrap.build_registry`.
- `orchestrator.py`: `run_hunt_cycle()` / `OrchestrationResult`. Sufficient evidence returns immediately: no ranking, hunt or telemetry. Otherwise tries ranked sources in order, each at most once, gated by `headroom_gate`, each attempt logged. Stops at the first hunt that resolves the verdict.
- `refresh_hook.py`: `make_refresh_and_research()`. Copies hunted files into `data/raw/<source_type>/`, re-runs `ingest.run_ingest.run()` (re-embeds changed files only), rebuilds the registry, re-answers through `Router.route()` + `compose(..., harden=True)`, re-evaluates.

## RegistryBridge timings

Verified against the 321,124-chunk Qdrant collection. CPU only, 3 consecutive `build_registry()` calls, not isolated from background load.

| mode | per build |
|---|---|
| `client=` passed (shared client) | ~35s |
| no client (`RegistryBridge(embedder)`) | ~78-104s |

- Without a shared client, a second `refresh_all()` raises `RuntimeError: Storage folder ... already accessed by another instance`.
- Pass `client=get_qdrant_client()` for more than one rebuild.

## Not included

- Live internet-fetch hunt source.
- Single real end-to-end run of hunt, ingest, reingest and re-answer. Each step is verified separately.

## Tests

```
pip install -e .[dev]
pytest
```

- 54 tests, hand-built fixtures, no live service, GPU or network.
- 40 need only the repo's `pip install -e .`.
- 14 (`test_headroom_gate.py`, `test_orchestrator.py`) need `rag-reliability` and skip without it.
- `headroom_gate.py` needs `numpy` (see `pyproject.toml`).
