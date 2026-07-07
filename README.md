# linkgraph

A standalone showcase repo: a cross-document relationship graph over
[agentic-rag](../agentic-rag)'s `data/entities/candidates.jsonl` entity-mention
stream. Builds a real, queryable graph of which RFCs obsolete/are obsoleted by
which others (a genuine many-to-many supersession graph, not a linear revision
chain), which errata correct which RFCs, and which entities are frequently
co-mentioned in the same source documents (a weaker, scored, undirected
signal). Hands off to [rag-reliability](../rag-reliability)'s `graphrx`
structural linter via a flattened export.

Work in progress, tested standalone — built and tested against hand-built
fixtures matching the real `candidates.jsonl` shape, AND against the real
21,830-mention `candidates.jsonl` export via `smoke_real_corpus.py`
(`python smoke_real_corpus.py`), which measured: 13,666 nodes, 14,844 edges
— `co_mentions=5061`, `obsoletes=2370`, `updates=2352`, `corrects=5061`.
Not yet wired into agentic-rag's answer path (a separate later step).
