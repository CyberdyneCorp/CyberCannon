"""Ports — the Protocols the adapters implement.

Each port is one question the core needs answered by the outside world, and
nothing more:

* :mod:`~cybercanon.application.ports.spec_store` — where specifications live
  (git is the source of truth; discovery walks upward, D9);
* :mod:`~cybercanon.application.ports.mesh_inspector` — mesh *reading*, the D1
  boundary: it returns dumb `MeshFacts` and the domain decides pass or fail;
* :mod:`~cybercanon.application.ports.blob_store` — where derived blobs go;
* :mod:`~cybercanon.application.ports.preview` — the value objects the two
  preview-facing ports share.

A port defines its own failure modes. Everything that means "the operation could
not run" subclasses :class:`~cybercanon.application.errors.OperationFailed`, so
an inbound adapter has one thing to catch and one exit code to map it to (D11).
"""
