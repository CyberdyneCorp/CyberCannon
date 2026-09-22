"""In-memory fakes, exercised by the per-port conformance suites and the BDD steps.

One constructor, used by every layer. A unit test, a BDD step and a port
conformance suite all build their fakes through :func:`build_fakes`, so a fake
cannot acquire one shape in the unit suite and another in the scenarios — which
is the same failure the port conformance suites exist to catch one level down
(a fake that lies about its adapter).

The registry is the single place a fake is declared:

```python
from cybercanon.application.testing.spec_store import InMemorySpecStore

FAKE_FACTORIES = MappingProxyType({"spec_store": InMemorySpecStore})
```

Ports arrive with the change that introduces them, and the change that adds a
port adds its fake here in the same breath. Everything downstream — the
``fakes`` BDD fixture, the conformance suites — then picks it up with no further
wiring. ``add-asset-spec-and-validator`` registers the three the validator needs:
``spec_store``, ``mesh_inspector`` and ``blob_store``. ``add-mcp-read-server``
adds the two the read surface needs: ``identity_provider`` and ``search_index``.
``add-web-backend`` adds the three the hosted surface needs: ``repository_host``,
``notifier`` and ``dismissals``, plus the two CyberdyneAuth brings for the
command line: ``credential_store`` and ``interactive_sign_in``.
``add-concept-ingestion`` adds the three ingestion needs: ``image_inspector``,
``thumbnail_renderer`` and ``view_index``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.credential_store import InMemoryCredentialStore
from cybercanon.application.testing.dismissals import InMemoryDismissals
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.image_inspector import InMemoryImageInspector
from cybercanon.application.testing.interactive_sign_in import InMemoryInteractiveSignIn
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.notifier import InMemoryNotifier
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.testing.thumbnail_renderer import InMemoryThumbnailRenderer
from cybercanon.application.testing.view_index import InMemoryViewIndex

FakeFactory = Callable[[], Any]
"""A zero-argument constructor for one port's in-memory fake."""

FAKE_FACTORIES: Mapping[str, FakeFactory] = MappingProxyType(
    {
        "blob_store": InMemoryBlobStore,
        "credential_store": InMemoryCredentialStore,
        "dismissals": InMemoryDismissals,
        "identity_provider": InMemoryIdentityProvider,
        "image_inspector": InMemoryImageInspector,
        "interactive_sign_in": InMemoryInteractiveSignIn,
        "mesh_inspector": InMemoryMeshInspector,
        "notifier": InMemoryNotifier,
        "repository_host": InMemoryRepositoryHost,
        "search_index": InMemorySearchIndex,
        "spec_store": InMemorySpecStore,
        "thumbnail_renderer": InMemoryThumbnailRenderer,
        "view_index": InMemoryViewIndex,
    }
)
"""Port name -> the fake that stands in for it. One entry per port."""


def fake_names(factories: Mapping[str, FakeFactory] | None = None) -> tuple[str, ...]:
    """The ports that have a fake, in a deterministic order."""
    return tuple(sorted(_registry(factories)))


def build_fakes(factories: Mapping[str, FakeFactory] | None = None) -> dict[str, Any]:
    """A fresh instance of every registered fake, keyed by its port name.

    Fresh on every call: a fake shared between two tests is a test that passes
    because of the one before it.
    """
    return {name: factory() for name, factory in sorted(_registry(factories).items())}


def _registry(factories: Mapping[str, FakeFactory] | None) -> Mapping[str, FakeFactory]:
    return FAKE_FACTORIES if factories is None else factories


__all__ = [
    "FAKE_FACTORIES",
    "FakeFactory",
    "InMemoryBlobStore",
    "InMemoryCredentialStore",
    "InMemoryDismissals",
    "InMemoryIdentityProvider",
    "InMemoryImageInspector",
    "InMemoryInteractiveSignIn",
    "InMemoryMeshInspector",
    "InMemoryNotifier",
    "InMemoryRepositoryHost",
    "InMemorySearchIndex",
    "InMemorySpecStore",
    "InMemoryThumbnailRenderer",
    "InMemoryViewIndex",
    "build_fakes",
    "fake_names",
]
