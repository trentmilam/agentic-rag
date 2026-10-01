# Consilium

Multi-RAG switchboard over separate document collections (legal contracts, market filings, an HR handbook).

- Routes a plain-language query to the collection that can answer.
- Cites the exact source.
- Abstains when nothing supports an answer.
- Router scores each query against module descriptors, selects those above a floor, fans out for cross-domain queries.
- Integrity gate checks every claim against its source passage.
- v1. Self-contained, deterministic, offline.

## Quickstart

```bash
# demo: route sample queries, show cited answers, abstention, and the integrity gate
python run_demo.py

# ...or ask your own question
python run_demo.py --query "What is the confidentiality term length in the mutual NDA?"

# --with-compute also registers the finance compute module, so a finance-math
# query routes to an audited computation instead of a retrieval module
python run_demo.py --with-compute --query "Black-Scholes call price for spot 100 strike 100 expiry 1 vol 0.2 rate 0.05"

# verify everything: all 5 evals (routing, integrity gate, hardening, compute
# routing, and the naive-RAG head-to-head), one aggregate PASS/FAIL
python eval/run_all.py
```

- Python 3.9+, standard library only.
- Pure-Python hashing embedder. No numpy, network or model download. Reproducible byte for byte.

## Head-to-head vs naive no-gate RAG

`eval/eval_baseline.py`. Same cases, corpus and embedder. Baseline is Consilium without its three gates: router abstention floor and anchor gate, integrity-gate claim binding, query-relevance floor.

| case-set (N) | naive baseline | Consilium |
|---|---|---|
| in-scope, answered with citations (11) | **11** | **11** |
| out-of-scope, confidently answered (4) | **4** ← hallucinates | **0** ← abstains |
| fabricated claim, emitted uncited (1) | **1** ← ships it | **0** ← dropped |
| **UNSAFE outputs (of 5)** | **5** | **0** |

Baseline emits 5/5 unsafe outputs, Consilium 0/5. In-scope recall is 11/11 for both. Re-run with `python eval/eval_baseline.py`.

## Results (`eval/eval.py`)

| metric | value | target |
|---|---|---|
| routing accuracy (single-domain query → correct module) | **1.000** (9/9) | ≥ 0.80 |
| fan-out (cross-domain query selects all relevant modules) | **1.000** (2/2) | == 1.00 |
| abstention (out-of-scope query refused, not answered) | **1.000** (2/2) | == 1.00 |
| citation coverage (every emitted claim bound to a source span) | **1.000** (11/11) | == 1.00 |
| fabricated-claim rejection (unsupported claim dropped by the gate) | **True** | True |

Adversarial case: an injected claim with no source ("Acme Corp secretly plans to acquire Globex...") is dropped.

## How it works

- Module (`consilium/module.py`): `{corpus, retriever, descriptor}`. Descriptor (`descriptor.json`): name, subjects, example queries, authority, freshness, trust_tier.
- Registry (`consilium/registry.py`): discovers modules on disk, exposes descriptors.
- Router (`consilium/router.py`): score = `0.45·descriptor-centroid + 0.20·best-chunk + 0.35·subject-overlap`. Selects every module above an absolute floor. Abstains when none clear it.
- Integrity gate (`consilium/integrity.py`): binds each claim to its best-supporting span. Unsupported claims are dropped. A wholly unsupported answer abstains.
- Composer (`consilium/composer.py`): assembles surviving claims into one cited answer.

Flow: `query → router (descriptors → module set | abstain) → per-module retrieve → integrity gate → composer → cited answer + routing/audit trace`.

## Demo modules

Synthetic, public-safe.

- markets: SEC-style filings, market glossary (revenue, EPS, EBITDA).
- legal: NDA / MSA templates, GDPR summary (confidentiality, IP, data rights).
- handbook: synthetic firm handbook (PTO, expenses, security policy).

Add a module: `modules/<name>/` with a `descriptor.json` and a `corpus/`.

Security: a `descriptor.json` with `"kind": "compute"` names a Python `module:class` that `Registry.load` dynamic-imports and instantiates (`consilium/registry.py`). Only point `modules_dir` at directories you trust. Disabled by default. Enable with `Registry.load(modules_dir, embedder, allow_compute_adapters=True)`. No shipped module uses `kind: "compute"`. The finance compute module is registered directly in Python.

## Scope and limitations (v1)

- Synthetic corpora only.
- Deterministic hashing retrieval. Optional LLM router/composer when a local model gateway is reachable (v2).
- Deferred to v2: UI/console, private/on-prem deployment with access control, real corpora.
- Open failure mode: `compose(..., query_relevance_floor=0.05)` is low. The router's anchor gate stops incidental-keyword out-of-scope cases (`eval/eval_baseline.py`: naive baseline's cited chunks at rel≈0.15–0.22, above 0.05). A jargon-heavy out-of-scope query naming ≥2 subject tokens can still slip the floor. Calibrating the floor is queued.
- Router floor/weights/anchor gates and the integrity-gate support floor (`consilium/router.py`, `consilium/composer.py`) are tuned on the shipped 16-case set (`eval/cases.json`). No held-out query set. The 1.000 numbers may not generalize past this corpus.

## Integrity hardening

Cross-corpus conflict detection with trust resolution. Corroboration-based poison quarantine. `consilium/hardening.py`, via `compose(..., harden=True)`.

```
python eval/eval_v2.py
```

eval_v2: exit 0, 11/11 checks.

- Cross-corpus conflict detected, resolved to the higher-trust source, loser surfaced.
- `$4.2 billion` vs `$4.2 million` flagged. `$4.2 billion` == `$4,200 million` not flagged. Incidental years/percents ignored.
- Intra-corpus poison quarantined, corroborated legit kept.
- Three exact poison copies all quarantined. Near-duplicates collapse to one source.
- Agreement and different-topic controls: zero false conflicts.

Limitations (deterministic heuristic; closing them needs an NLI / trust-provenance layer):

- Numeric magnitudes only. Word-spelled numbers and non-numeric conflicts ("Delaware" vs "Nevada") are not detected.
- Same-magnitude different-metric claims (revenue vs net income) can false-positive if textually similar.
- Paraphrase-flooding is not defeated by dedup. Needs per-source trust / provenance / signing.
- Count-based corroboration is advisory. Ambiguous conflicts are flagged, not resolved.

## Heterogeneous routing (retrieval + compute)

One router over retrieval and compute modules. A `ComputeModule` (`consilium/compute.py`) has a descriptor and returns an audited, deterministic computation instead of a passage. Invalid input returns `{ok: False, tool, error}`, same as unparseable input. Demo: `python run_demo.py --with-compute --query "..."`.

```
python eval/eval_v3.py
```

eval_v3: exit 0, 5/5.

- Finance-math query routes to the compute module, returns Black-Scholes 10.450584.
- Policy question routes to a retrieval module (handbook).
- Out-of-scope query abstains.
- Retrieval and hardening evals still green.

## Generic compute adapters

`consilium/capability.py` documents the contract the router/composer need: `name`, `descriptor`, `chunks`, `centroid()`, `retrieve()`. `Registry.load` registers a `kind: "compute"` module from disk by importing the `adapter` class named in its `descriptor.json` (opt-in via `allow_compute_adapters=True`).

```
python eval/eval_core.py
```

eval_core: exit 0, 3/3.

- Query anchoring only the compute module: heterogeneous-routing response shape unchanged.
- Query anchoring a compute and a retrieval module: audited computation and cited text answer.
- Throwaway disk-registered `kind: "compute"` module loads and runs through `Registry.load`.

## License

MIT. See [LICENSE](LICENSE).
