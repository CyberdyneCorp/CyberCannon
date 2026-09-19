"""Export fixtures, built at test time rather than committed as binaries.

The domain suite runs over hand-built `MeshFacts` with zero files on disk (D1),
and that is deliberately not what this package is for. `TrimeshInspector` reads
actual files, so the only way to know it reads them *correctly* is to hand it
actual files — and the only way to do that without binary blobs rotting in git
is to write them from code, from one place, so a fixture's contents are readable
rather than archaeological.

`canon_fixtures.mesh` writes the glTF and OBJ exports the port conformance suite
and the opt-in integration suite use: a skinned, animated GLB, the same export
as `.gltf`, a rigged GLB with two named parts and a 74-bone skeleton (what the
`asset-preview` scenarios name), a static GLB, a static OBJ, an OBJ with two
named objects (what an artist actually exports, and what a single-object fixture
cannot ask a reader about), and a file that is not the mesh its extension
claims. The skinned writers take their clips as an argument, so the same asset
can be written to glTF and to FBX carrying the same clip names and durations —
which is what task 7.5's cross-format coverage comparison needs in order to be
comparing one contract rather than two assets. `canon_fixtures.fbx` writes the binary FBX
ones — a skinned, animated quadruped rig with three named clips, a static prop,
and the two shapes the reader must refuse — and is cross-checked against
Blender's own importer in
`tests/integration/test_fbx_against_blender.py`.
"""
