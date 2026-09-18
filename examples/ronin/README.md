# `ronin` — a worked game repository

A complete, validating example of what adopting CyberCanon looks like in a game
repository. CI runs it: `tests/integration/test_worked_example.py` copies this
directory, writes the export, and checks, validates and compiles it through the
`canon` binary — so an example that drifts from the tool fails the build.

```
.canon/project.yaml                  project defaults, severities, preview settings
characters/mech_scout/asset.yaml     the contract: concept, design, constraints
characters/mech_scout/art-spec.md    the compiled briefing — derived, never edited
```

**The export is not committed**, here or anywhere else: nothing binary lives in
git. `characters/mech_scout/exports/SM_mech_scout_LOD0.glb` is written from code
by `tools/canon_fixtures` when the test runs. In a real repository it is the file
your artist exports from Blender.

Try it:

```sh
canon check                                                   # the spec files themselves
canon validate characters/mech_scout/exports/SM_mech_scout_LOD0.glb
canon compile --stdout characters/mech_scout/asset.yaml       # regenerates art-spec.md
```

`mech_scout` is skinned and animated. It declares an attachment point
(`SOCKET_muzzle_l`), two design states that resolve into required animation
clips through the project's `clip_naming` convention, and a rig the project's
bone budget applies to — so every one of those is a gate the export has to pass,
not a note somebody has to remember.
