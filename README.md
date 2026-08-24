# linkgraph

[![tests](https://github.com/trentmilam/linkgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/trentmilam/linkgraph/actions/workflows/ci.yml)

**A queryable relationship graph across documents — which RFC obsoletes which, which
erratum corrects what, and which entities keep turning up together — built from a real
21,830-mention extraction, not a fixture.**

Retrieval systems treat documents as independent chunks. They are not. An RFC is
superseded by six others; an erratum corrects a specific section; two protocols are
discussed together often enough that the co-occurrence is itself a signal. `linkgraph`
turns an entity-mention stream into a graph of those relationships and lets you ask
about them directly.

Pure standard library. Deterministic. Fully offline.

## Measured on the real corpus

`python smoke_real_corpus.py`, against the entity-mention export produced by
[agentic-rag](https://github.com/trentmilam/agentic-rag)'s ingest of the live IETF RFC
ecosystem:

| | |
|---|---:|
| mentions loaded | 21,830 |
| nodes | 13,666 |
| edges | 14,844 |
| ` ` `co_mentions` | 5,061 |
| ` ` `obsoletes` | 2,370 |
| ` ` `updates` | 2,352 |
| ` ` `corrects` | 5,061 |

Every one of those seven numbers is **asserted** by that script, not merely printed — if
the graph changes shape, the script fails and names the figure this README publishes.
That was a real gap: it used to assert only `corrects > 0`, which a graph half this size
would have passed just as happily.

## What the edges mean

- **`obsoletes` / `updates`** — the genuine IETF supersession relation, recovered from
  the RFC index. It is many-to-many, not a linear revision chain: RFC 2616 is obsoleted
  by six separate RFCs (7230–7235), and a graph is the honest representation of that. A
  "latest version" pointer would have to pick one and be wrong.
- **`corrects`** — a community-submitted erratum against a specific RFC.
- **`co_mentions`** — a scored, undirected, deliberately weaker signal: two entities
  cited in the same source document. Useful for neighbourhood expansion, never treated
  as a factual claim.

## Where it is used

`linkgraph` backs the relationship tools in
[agentic-rag](https://github.com/trentmilam/agentic-rag)'s MCP server — `get_related`
dispatches into it through that repo's `agenticrag/relationships.py` bridge. It is
deliberately kept separate from agentic-rag's own `SupersessionModule`, which answers
the same obsoletion questions from an independently built source, so the two can be
cross-checked against each other over the same underlying IETF facts. It is not in the
chat answer path; the demo and eval there never import it.

It also exports a flattened graph for the `graphrx` structural linter in
[rag-reliability](https://github.com/trentmilam/rag-reliability), which checks the result
for the entity-merge defects that corrupt downstream answers.

## Quickstart

```bash
git clone https://github.com/trentmilam/linkgraph
cd linkgraph
python -m pytest -q          # 50 tests, no dependencies, ~0.2s
python run_demo.py           # builds a graph from the bundled fixtures and queries it
```

```python
from linkgraph import build_graph
from linkgraph.adapter import load_from_export

graph = build_graph(load_from_export("path/to/candidates.jsonl"))

# RFC 2616 is obsoleted by six RFCs at once. The component branches, so the
# whole thing comes back rather than one arbitrarily-chosen "latest".
graph.get_obsoletion_chain("RFC2616")["status"]        # -> "obsoleted"

graph.get_related("rfc:RFC2616", max_hops=1, edge_types=["obsoletes"])
# -> [('rfc:2068', 1), ('rfc:7230', 1), ('rfc:7231', 1), ('rfc:7232', 1),
#     ('rfc:7233', 1), ('rfc:7234', 1), ('rfc:7235', 1)]

graph.get_corrections("RFC2616")[:5]
# -> ['1483', '1619', '2301', '2645', '2806']
```

## Reproducing the corpus numbers

`smoke_real_corpus.py` reads `agentic-rag/data/entities/candidates.jsonl` and does not
fetch or ingest anything itself. To regenerate that file, run agentic-rag's ingest — it
is a multi-hundred-megabyte fetch from the IETF and takes minutes on a GPU or hours on
CPU, which is why it is not committed here. The 50-test suite needs none of it.

## Honest scope

- The `graphrx` hand-off — and only that hand-off — needs the `rag-reliability` sibling
  cloned next to this repo. The core graph builds and every other test runs without it.
- `co_mentions` is a co-occurrence heuristic. It says two things were discussed together,
  which is not a claim that they are related.
- Entity resolution is exact-identifier matching on RFC/errata numbers. It does not
  attempt fuzzy name resolution, and would need real work before it could.
- `store.py` provides SQLite persistence and is tested, but nothing in the demo or eval
  path uses it yet.

## License

MIT.
