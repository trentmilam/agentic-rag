"""Tests for activerag.registry_bridge.

Hermetic: RegistryBridge is driven entirely by a hand-built FakeBuildRegistry
that returns distinguishable fake Registry-shaped objects -- no real Qdrant,
embedder, or agentic-rag registry is ever built or touched. The real
``agenticrag.bootstrap.build_registry`` function is referenced ONLY as a
function object (to prove the injection point's default really is wired to
it) and is never invoked -- matching the no-live-dependency style of the other
activerag tests.
"""
from __future__ import annotations

import inspect

from activerag.registry_bridge import RegistryBridge


class FakeRegistry:
    """A minimal stand-in for consilium.registry.Registry: distinguishable by
    its own ``build_id`` (and the embedder/client it was built with) so a test
    can prove a genuinely NEW object was swapped in, not the same one reused."""

    def __init__(self, build_id, embedder, client):
        self.build_id = build_id
        self.embedder = embedder
        self.client = client
        self.modules = [f"module-from-build-{build_id}"]


class FakeBuildRegistry:
    """Fake build_registry(embedder, client=None) -> FakeRegistry. Records every
    call's args and hands back a fresh FakeRegistry with an incrementing
    build_id each call, so identity/distinctness is directly checkable."""

    def __init__(self):
        self.calls = []
        self._next_id = 0

    def __call__(self, embedder, client=None):
        self.calls.append((embedder, client))
        self._next_id += 1
        return FakeRegistry(self._next_id, embedder, client)


def test_default_build_registry_is_the_real_agentic_rag_bootstrap_function():
    # The injection point defaults to the REAL agenticrag.bootstrap.build_registry.
    # Checked via the constructor's default parameter value only -- never called,
    # never instantiated with it -- so this proves the wiring without ever
    # touching Qdrant.
    from agenticrag.bootstrap import build_registry as real_build_registry

    default = inspect.signature(RegistryBridge.__init__).parameters["build_registry"].default
    assert default is real_build_registry


def test_construction_builds_the_initial_registry_via_injected_build_registry():
    fake_build = FakeBuildRegistry()
    embedder = object()
    client = object()

    bridge = RegistryBridge(embedder, client=client, build_registry=fake_build)

    assert fake_build.calls == [(embedder, client)]
    assert bridge.registry.build_id == 1
    assert bridge.registry.embedder is embedder
    assert bridge.registry.client is client


def test_refresh_all_calls_the_injected_build_registry_with_the_constructed_args():
    fake_build = FakeBuildRegistry()
    embedder = object()
    client = object()
    bridge = RegistryBridge(embedder, client=client, build_registry=fake_build)

    bridge.refresh_all()

    # Called once at construction, once at refresh_all -- both with the SAME
    # embedder/client the bridge was constructed with.
    assert fake_build.calls == [(embedder, client), (embedder, client)]


def test_refresh_all_genuinely_replaces_the_held_registry_not_mutates_it():
    fake_build = FakeBuildRegistry()
    bridge = RegistryBridge(object(), build_registry=fake_build)
    before = bridge.registry

    after = bridge.refresh_all()

    assert after is bridge.registry            # refresh_all returns the new held registry
    assert after is not before                  # a genuinely NEW object, not the same one
    assert before.build_id == 1
    assert after.build_id == 2                  # distinguishable fake proves it's a different build


def test_repeated_refresh_all_keeps_swapping_without_accumulating_old_registries():
    fake_build = FakeBuildRegistry()
    bridge = RegistryBridge(object(), build_registry=fake_build)

    seen = [bridge.registry]
    for _ in range(4):
        seen.append(bridge.refresh_all())

    # Every swap produced a distinct object (no reuse/caching) ...
    assert len({id(r) for r in seen}) == len(seen)
    assert [r.build_id for r in seen] == [1, 2, 3, 4, 5]
    # ... and the bridge holds ONLY the latest one.
    assert bridge.registry is seen[-1]
    # No hidden history/accumulator attribute leaking old registries anywhere
    # on the bridge -- its instance state is exactly these four attributes.
    assert set(vars(bridge)) == {"_embedder", "_client", "_build_registry", "_registry"}


def test_importing_registry_bridge_never_pulls_in_qdrant_client():
    import sys

    assert "qdrant_client" not in sys.modules
