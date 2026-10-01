# linkgraph

Relationship graph over documents: RFC obsoletes/updates, errata corrections, entity co-mentions.

Built from a 21,830-mention extraction of the IETF RFC corpus. Standard library only. Deterministic. Offline.

## Real corpus

`python smoke_real_corpus.py`, against the entity-mention export from [agentic-rag](https://github.com/trentmilam/agentic-rag)'s ingest.

| | |
|---|---:|
| mentions loaded | 21,830 |
| nodes | 13,666 |
| edges | 14,844 |
| ` ` `co_mentions` | 5,061 |
| ` ` `obsoletes` | 2,370 |
| ` ` `updates` | 2,352 |
| ` ` `corrects` | 5,061 |

The script asserts all seven numbers.

## Edge types

- `obsoletes` / `updates`: IETF supersession from the RFC index. Many-to-many. RFC 2616 is obsoleted by six RFCs (7230-7235).
- `corrects`: community-submitted erratum against a specific RFC.
- `co_mentions`: scored, undirected. Two entities cited in the same source document.

## Used by

- [agentic-rag](https://github.com/trentmilam/agentic-rag) MCP server: `get_related` via `agenticrag/relationships.py`. Not in the chat answer path.
- Separate from agentic-rag's `SupersessionModule` (independent source for the same obsoletion questions).
- Flattened export for the `graphrx` linter in [rag-reliability](https://github.com/trentmilam/rag-reliability).

## Quickstart

`packages/linkgraph` in the `agentic-rag` monorepo. From the repo root, after `pip install -e .`:

```bash
python -m pytest packages/linkgraph -q   # 43 tests pass standalone in ~0.2s
                                          # (7 more run, 50 total, once the rag-reliability sibling is cloned)
python packages/linkgraph/run_demo.py    # builds a graph from the bundled fixtures and queries it
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

## Regenerating the corpus numbers

- `smoke_real_corpus.py` reads `agentic-rag/data/entities/candidates.jsonl`.
- To regenerate it, run agentic-rag's ingest: multi-hundred-megabyte IETF fetch, minutes on GPU, hours on CPU. Not committed.
- The 50-test suite does not need it.

## Limitations

- `graphrx` hand-off needs the `rag-reliability` sibling cloned next to agentic-rag. Nothing else does.
- `co_mentions` is a co-occurrence heuristic. Not a claim that the entities are related.
- Entity resolution is exact-identifier matching on RFC/errata numbers. No fuzzy names.
- `store.py` (SQLite persistence) is tested but unused by the demo and eval.

## License

MIT.
