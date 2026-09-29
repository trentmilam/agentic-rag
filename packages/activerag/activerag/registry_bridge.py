"""registry_bridge: swap the entire agentic-rag Registry, atomically.

The one live dependency :mod:`activerag.orchestrator`'s ``refresh_and_research``
hook needs but does not itself construct (see the injection-point note in
``orchestrator.py``'s module docstring) is a real, queryable Consilium
``Registry`` backed by agentic-rag's Qdrant collection. This module is the
entry point that builds, and periodically rebuilds, that Registry, the same
way ``agenticrag/bootstrap.py`` is the entry point that builds it the first
time for agentic-rag's own app.

Lazy build_registry resolution
-------------------------------
Importing this module touches nothing from ``agenticrag``: the real
``agenticrag.bootstrap.build_registry`` is resolved lazily, inside
:func:`_load_real_build_registry`, and only when a :class:`RegistryBridge` is
constructed without an injected ``build_registry``. A consumer that injects
its own builder, which every test in this repo does, never triggers that
resolution at all.

``agenticrag`` and ``consilium`` are both packages of this same repository
(mapped by the root ``pyproject.toml`` and importable after
``pip install -e .``), so no ``sys.path`` insert is needed to reach either one.

The lazy resolution still only imports the ``build_registry`` function.
``agenticrag.bootstrap``'s own top-level imports are all dependency-light
(dataclasses/json/os/re, no ``qdrant_client``, no embedder library); the
Qdrant-touching work is entirely inside ``build_registry()``'s own function
body (and deferred further still, inside ``agenticrag.registry_loader``). So
resolving the real ``build_registry`` never opens a Qdrant client. Only
actually calling it (at construction, or inside
:meth:`RegistryBridge.refresh_all`) does.

Wholesale swap, not in-place mutation
--------------------------------------
``consilium.registry.Registry`` is just ``self.modules = modules``, a plain
list with no external handles into it. So :meth:`RegistryBridge.refresh_all`
rebuilds a whole new ``Registry`` (by calling ``build_registry`` again, with
the same embedder/client this bridge was constructed with) and replaces the
held reference outright, rather than mutating the old registry's modules in
place or doing a targeted per-source_type refresh. A wholesale swap is atomic
from any caller mid-read of ``.registry``: they either see the whole old
Registry or the whole new one, never a half-updated one. It also reuses
``build_registry`` itself, an already-tested code path, instead of a second,
parallel, partial-refresh implementation.

Injectable ``build_registry`` (fixture-testable without live Qdrant)
----------------------------------------------------------------------
As :mod:`activerag.orchestrator` injects ``refresh_and_research`` /
``gate`` / ``hunt_sources`` rather than hard-coding them, :class:`RegistryBridge`
takes ``build_registry`` as a constructor parameter, defaulting (lazily, via
:func:`_load_real_build_registry`, see above) to the real
``agenticrag.bootstrap.build_registry``. A test supplies a fake callable that
returns distinguishable fake-Registry-shaped objects instead, so the swap
behavior (right args, genuine replacement, repeated swaps) is fully
fixture-tested with no live Qdrant, embedder, or GPU anywhere in the test
process.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from activerag._paths import add_sibling_paths

add_sibling_paths()

if TYPE_CHECKING:  # typing only; see the module docstring for why this
    # module never needs a hard runtime import of consilium itself.
    from consilium.registry import Registry

__all__ = ["BuildRegistry", "RegistryBridge"]

# The injected registry-builder: same (embedder, client=...) -> Registry shape
# as the real agenticrag.bootstrap.build_registry. A plain Callable alias so a
# fixture-test fake and the real function are interchangeable without this
# module caring which one it was handed.
BuildRegistry = Callable[..., "Registry"]


def _load_real_build_registry() -> "BuildRegistry":
    """Resolve the real ``agenticrag.bootstrap.build_registry``, lazily.

    Called only when a :class:`RegistryBridge` is constructed without an
    injected ``build_registry``, never at module import time (see the module
    docstring's "Lazy build_registry resolution" section for why that
    boundary matters). Resolving the function opens no Qdrant client; only
    calling it does.
    """
    from agenticrag.bootstrap import build_registry

    return build_registry


class RegistryBridge:
    """Holds one live ``Registry`` reference and knows how to swap it wholesale.

    Constructed with the ``embedder``/``client`` a real ``build_registry`` call
    needs (the same pair agentic-rag's own ``bootstrap.build_registry`` takes),
    plus an optional ``build_registry`` override for tests. Left unset, the
    real ``agenticrag.bootstrap.build_registry`` is resolved lazily here, at
    construction time (see :func:`_load_real_build_registry`). The initial
    ``Registry`` is built the same way, via ``build_registry``, as every
    later refresh, so construction and refresh share one code path.
    """

    def __init__(
        self,
        embedder,
        client=None,
        *,
        build_registry: "BuildRegistry | None" = None,
    ) -> None:
        self._embedder = embedder
        self._client = client
        if build_registry is None:
            build_registry = _load_real_build_registry()
        self._build_registry = build_registry
        self._registry = self._build_registry(self._embedder, client=self._client)

    @property
    def registry(self):
        """The currently-held ``Registry``. Read this fresh after every
        :meth:`refresh_all`; do not cache it across a refresh."""
        return self._registry

    def refresh_all(self):
        """Rebuild the whole registry and swap it in wholesale (see module docstring).

        Calls ``build_registry(embedder, client=client)`` again with the same
        embedder/client this bridge was constructed with, then replaces
        ``self._registry`` outright with the freshly-built Registry. The old
        one is simply dropped, never mutated in place. Returns the new
        Registry for convenience.
        """
        self._registry = self._build_registry(self._embedder, client=self._client)
        return self._registry
