"""Export fixtures, built at test time rather than committed as binaries.

The domain suite runs over hand-built `MeshFacts` with zero files on disk (D1),
and that is deliberately not what this package is for. `TrimeshInspector` reads
actual files, so the only way to know it reads them *correctly* is to hand it
actual files — and the only way to do that without binary blobs rotting in git
is to write them from code, from one place, so a fixture's contents are readable
rather than archaeological.

`canon_fixtures.mesh` writes the exports the port conformance suite and the
opt-in integration suite use: a skinned, animated GLB, a static GLB, a static
OBJ, and a file that is not the mesh its extension claims.
"""
