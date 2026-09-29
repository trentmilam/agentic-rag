"""activerag: the Consilium-aware half of a self-extending RAG mechanism.

See ``README.md`` for scope and status. The package is a complete, bounded
hunt-and-retry cycle over a Consilium answer: :mod:`activerag.evidence` (detect
thin evidence), :mod:`activerag.priority` (rank which source to hunt first),
:mod:`activerag.hunt` (a staging-directory hunt source),
:mod:`activerag.headroom_gate` (is there physical room to hunt?),
:mod:`activerag.orchestrator` (the bounded conductor),
:mod:`activerag.registry_bridge` + :mod:`activerag.refresh_hook` (the real
re-ingest/re-answer wiring against agentic-rag's registry), and
:mod:`activerag.telemetry` (an append-only audit trail). Every module is
independently testable against hand-built fixtures with no live Qdrant/GPU.
"""
