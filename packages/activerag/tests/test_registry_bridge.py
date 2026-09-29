"""Tests for activerag.registry_bridge.

Hermetic: RegistryBridge is driven entirely by a hand-built FakeBuildRegistry
that returns distinguishable fake Registry-shaped objects: no real Qdrant,
embedder, or agentic-rag registry is ever built or touched. The real
``agenticrag.bootstrap.build_registry`` function is referenced ONLY as a
function object (to prove the lazy default really resolves to it) and is
never invoked; the one test that references it skips cleanly when the
agentic-rag / consilium sibling clones are absent, matching the
no-live-dependency style of the other activerag tests.
"""
from __future__ import annotations

import inspect
import subprocess
import sys

import pytest

import activerag.registry_bridge as registry_bridge_module
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


def test_default_build_registry_resolves_lazily_at_construction(monkeypatch):
    # The injection point's default is None, resolved through
    # _load_real_build_registry at CONSTRUCTION time, never at module import
    # (that lazy boundary is what lets this whole file collect with no sibling
    # repo cloned). Proven hermetically: swap the loader for one that returns a
    # fake, construct with no build_registry argument, and the loaded fake must
    # be exactly what the bridge builds with.
    default = inspect.signature(RegistryBridge.__init__).parameters["build_registry"].default
    assert default is None

    fake_build = FakeBuildRegistry()
    loader_calls = []

    def fake_loader():
        loader_calls.append(True)
        return fake_build

    monkeypatch.setattr(registry_bridge_module, "_load_real_build_registry", fake_loader)
    embedder = object()
    bridge = RegistryBridge(embedder)

    assert loader_calls == [True]
    assert fake_build.calls == [(embedder, None)]
    assert bridge.registry.build_id == 1


def test_lazy_loader_resolves_the_real_agentic_rag_bootstrap_function():
    # The lazy loader really returns the REAL agenticrag.bootstrap.build_registry,
    # referenced as a function object only, never called, so no Qdrant is
    # touched. Resolving it genuinely needs the agentic-rag sibling clone (whose
    # bootstrap in turn hard-imports from its own consilium sibling); skip
    # cleanly when either is absent instead of failing the run.
    try:
        resolved = registry_bridge_module._load_real_build_registry()
    except ModuleNotFoundError as exc:
        pytest.skip(f"needs the agentic-rag (+ consilium) sibling clones: {exc}")

    from agenticrag.bootstrap import build_registry as real_build_registry

    assert resolved is real_build_registry


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

    # Called once at construction, once at refresh_all, both with the SAME
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
    # on the bridge; its instance state is exactly these four attributes.
    assert set(vars(bridge)) == {"_embedder", "_client", "_build_registry", "_registry"}


def test_importing_registry_bridge_never_pulls_in_qdrant_client():
    """Importing this module must not drag in the Qdrant client.

    That is the point of resolving ``build_registry`` lazily: merely importing (or
    test-collecting) registry_bridge should stay dependency-light.

    A subprocess is used here for a reason. This used to assert on the ambient ``sys.modules``
    of the test session, which proved nothing about this module's import; it held
    only because activerag was its own repository and nothing else in that session
    had any reason to import qdrant_client. Here other suites import it perfectly
    legitimately, and the assertion began failing over an import it was never really
    measuring. A fresh interpreter measures the thing the name claims."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; import activerag.registry_bridge; "
         "sys.exit(1 if 'qdrant_client' in sys.modules else 0)"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "importing activerag.registry_bridge pulled in qdrant_client\n" + result.stderr
    )
