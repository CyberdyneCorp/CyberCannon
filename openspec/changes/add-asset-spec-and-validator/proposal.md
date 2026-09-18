# Proposal

## Why

Today nothing in the pipeline states what a concept *means* in verifiable terms.
Art and code argue about silhouettes with no shared artifact, design intent lives
in Discord, and a modeller can spend three days on a mesh before anyone checks
whether it fits the triangle budget, the pivot convention, or the sockets the VFX
code expects. The expensive failure — **days lost per asset** — is the missing
contract, not the missing viewer.

This change creates that contract (`asset.yaml`) and the machine that enforces it
(`canon validate`). It is **roadmap positions 1–2**, and it comes first for one
reason: it delivers value on day one to programmers through a pre-commit hook and
a CLI, **without asking a single artist to change a habit**, while every later
surface — MCP server, 2D model sheet, 3D viewer — is just a way to read, produce
or enforce this same file. Building any UI before the schema means rebuilding the
UI when the schema turns out wrong.

A second, quieter reason: the validator **depersonalises feedback**. The linter
rejects the file; the programmer does not reject the artist. That removes much of
the social friction in the original problem before any collaboration feature
exists.

## What Changes

- **`asset.yaml` schema** — a per-asset, in-repo contract with three authored
  blocks: `concept` (art), `design` (game design), `constraints` (engineering),
  plus identity (`id`, `name`, `aliases`), tri-owner fields, a `status` lifecycle
  (`concept → approved → modeling → validated → in-engine`), `links`, and an
  `annotations` block whose entries carry durable dual anchors.
- **Git as the source of truth** — the file lives next to the asset in the game
  repo. This change introduces **no database**: versioning, diff, blame and
  review are git's job.
- **Pure-domain validation rules** — `Rule`, `Violation`, `Report` evaluated
  against a `MeshFacts` value object (triangles, objects, transforms applied,
  unit scale, up axis, UV sets, materials, empties, animation clips, frame rate,
  skinning and bone count). Rules cover triangle and LOD budgets, naming
  convention, unit scale, up axis, unapplied transforms, texture sets, and
  **required sockets declared by design** — the closed loop where a designer's
  `SOCKET_muzzle_l` becomes a mechanically enforced export gate.
- **The same closed loop for animation** — `design.states` stops being a list of
  words. Each state resolves, through a clip naming convention, to a **required
  animation clip**; a declared state with no matching clip in the export is a
  violation naming the missing clip and the state that required it, extra clips
  are not violations, and a skeleton over `rig.max_bones` fails the export. States
  that genuinely have no animation must say so explicitly. Without this, `states`
  constrained nothing and was not checkable — a direct breach of the golden rule
  in `openspec/project.md`, and the reason the 3D viewer would have had nothing
  reliable to play.
- **A per-format fact capability matrix** — one declaration of which facts
  `GLB`/`GLTF`, `FBX` and `OBJ` can each yield. A rule whose facts a format cannot
  record is reported as **not evaluated**, naming the rule and the reason; it is
  never silently passed. A format that cannot *contain* what the spec demands —
  `OBJ` for an asset with animation clips, a rig or sockets — is reported as an
  unsuitable export format. The alternative, which is what an unstated matrix
  gives you, is a green run on a file where half the contract was never checked.
- **`canon` CLI** — `canon validate`, `canon compile`, `canon lint`, usable as a
  pre-commit hook, with stable exit codes and both human and JSON output.
- **Decimated preview GLB** — emitted as a by-product of the validation run that
  already loaded the mesh, so no 200 MB working export is ever served to a
  browser later.
- **`art-spec.md` compiler** — renders an asset's spec for humans and for agents
  reading the repo, containing **rules plus open issues only**. Resolved
  annotations are excluded; they live in git history where no context window pays
  for them.
- **No identity, no network in the validation path** — `canon validate` reads
  files and returns violations. If it ever required CyberdyneAuth, an auth outage
  or a missing VPN would block a commit and the tool would become the enemy.

## Capabilities

### New Capabilities

- `asset-spec`: the `asset.yaml` contract — identity, aliases, ownership, the
  three authored blocks, the state-to-clip animation contract and its naming
  convention, status lifecycle, links, annotation entries with dual anchors, and
  what makes a spec file itself valid.
- `asset-validation`: evaluating an exported mesh against an asset's constraints
  and design declarations — the rule set (budgets, conventions, sockets, animation
  clips, rig budget), the `MeshFacts` boundary, the per-format fact capability
  matrix and the not-evaluated outcome, violation severity, report shape, and
  determinism/offline guarantees.
- `asset-preview`: producing a decimated, compressed preview mesh — clips and
  skinning intact — as a by-product of validation, so downstream surfaces never
  load the working export and the 3D viewer plays animation from the preview.
- `spec-compilation`: compiling `asset.yaml` into `art-spec.md` for humans and
  agents — rules plus open issues, never the dead thread archive.
- `canon-cli`: the `canon` command surface — subcommands, exit codes, output
  formats, repo/asset discovery, and pre-commit usage.

### Modified Capabilities

None — this is the project's first change.

## Non-goals

Explicitly **not** in this change:

- **No web application.** No asset browser, no spec editor, no 2D model sheet, no
  3D viewer, no pin UI, no Svelte code at all.
- **No MCP server.** `where_is`, `get_asset_spec`, `validate_export` and friends
  are the next change; they depend on this contract existing.
- **No annotation authoring.** The schema *defines* the annotation entry and the
  compiler *honours* rule-vs-issue triage, but nothing in this change creates,
  resolves or promotes an annotation. Anchor re-projection and orphan detection
  belong to the viewer changes.
- **No PostgreSQL, no MinIO, no search index.** The cache/index layer arrives when
  there is a surface that needs to query across assets.
- **No CyberdyneAuth integration and no `Actor`/`Role` authorization.** The
  validator must run with no identity; identity enters with the first networked
  surface.
- **No CyberArche integration.** Linking long-form GDD documents is spec'd when
  the web surface exists; here `links` merely stores the URL.
- **No engine importer and no Blender add-on.**
- **No `.blend` parsing, deliberately.** Reading `.blend` means depending on a
  specific Blender version's Python runtime inside the validator — a heavyweight,
  version-fragile dependency in the one code path that must run everywhere with no
  setup, including a pre-commit hook on a programmer's machine that has no Blender
  installed. The contract is enforced on the **export**, which is also the artifact
  the engine consumes; the `.blend` is recorded in `links` and never parsed.
  Supported inputs are `GLB`/`GLTF`, `FBX` and `OBJ`, with `OBJ` governed by the
  capability matrix above.
- **No animation playback and no clip authoring.** This change decides whether the
  declared clips *exist and conform*; playing them is the 3D viewer's job, and
  authoring them is Blender's. No retargeting, no curve inspection, no per-keyframe
  analysis beyond the facts the matrix lists.
- **No AI auto-correction loop.** The validator reports; it never rewrites a mesh.

## Impact

- **New code** — `libs/cybercanon/domain/` (asset, spec blocks, constraints,
  anchors, state-to-clip resolution, the format capability matrix, rules,
  violations, report, status), `libs/cybercanon/application/`
  (ports `SpecStore`, `MeshInspector`, `BlobStore`; use cases `validate_export`,
  `compile_spec`, `lint_spec`; in-memory fakes),
  `libs/cybercanon/adapters/outbound/{git,mesh,fs}`,
  `libs/cybercanon/adapters/inbound/cli`, `services/cybercanon/cli`.
- **New dependencies** — `trimesh`, `pygltflib` (mesh reading and Draco-compressed
  GLB output), `pydantic` (schema parsing/validation), `typer` (CLI), `ruamel.yaml`
  (comment-preserving YAML round-trip), `pytest`, `import-linter`.
- **Repo conventions established** — the hexagonal layout, the import-linter
  contract (`domain ← application ← adapters`, inbound never imports outbound),
  and the rule that every inbound adapter delegates to the same use case. Later
  changes inherit these rather than re-deciding them.
- **Report shape impact** — a validation result now carries three per-rule
  outcomes (passed, violated, not evaluated) instead of two, and records the
  export's format. Every consumer specified later — the MCP `validate_export`
  tool, the web Validate button, CI — inherits that shape, which is why it is
  settled here rather than retrofitted once three surfaces render reports.
- **Consumer-side impact** — a game repo adopting CyberCanon gains
  `<asset>/asset.yaml` files, an optional `.canon/project.yaml` holding
  project-wide defaults (naming pattern, clip naming convention, default frame
  rate, up axis, unit scale, rig bone budget, engine content root), and a
  pre-commit hook entry. Engine target (Unreal or Unity) is a project-level
  configuration value, not a hardcoded assumption.
- **Export workflow impact** — a team exporting animated assets as `OBJ` will be
  told so on the first run rather than discovering at integration time that no
  animation rule ever ran. That is a deliberate, visible cost at adoption.
