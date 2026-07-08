# linkgraph

A cross-document relationship graph over
[agentic-rag](https://github.com/trentmilam/agentic-rag)'s `data/entities/candidates.jsonl`
entity-mention stream. Builds a real, queryable graph of which RFCs obsolete/are obsoleted by
which others (a genuine many-to-many supersession graph, not a linear revision
chain), which errata correct which RFCs, and which entities are frequently
co-mentioned in the same source documents (a weaker, scored, undirected
signal). Hands off to [rag-reliability](https://github.com/trentmilam/rag-reliability)'s `graphrx`
structural linter via a flattened export.

Work in progress — built and tested against hand-built
fixtures matching the real `candidates.jsonl` shape, AND against the real
21,830-mention `candidates.jsonl` export via `smoke_real_corpus.py`
(`python smoke_real_corpus.py`), which measured: 13,666 nodes, 14,844 edges
— `co_mentions=5061`, `obsoletes=2370`, `updates=2352`, `corrects=5061`.
Not yet wired into agentic-rag's answer path (a separate later step).

## Requires the rag-reliability sibling

The graph itself builds on its own, but the `graphrx` hand-off — and the eval that
exercises it — imports [rag-reliability](https://github.com/trentmilam/rag-reliability)'s
`graphrx` linter by putting the sibling repo on `sys.path`; it is not pip-installed. Clone
rag-reliability next to this repo:

```
git clone https://github.com/trentmilam/rag-reliability
```

so `linkgraph/` and `rag-reliability/` sit side by side. `linkgraph/_paths.py` resolves
`../rag-reliability/graphrx` from there. Without it the core graph still builds; only
`eval.py`'s graphrx hand-off will not import.
