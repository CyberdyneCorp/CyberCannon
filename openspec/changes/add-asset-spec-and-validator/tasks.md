# Tasks

## 1. Repository skeleton and layering contract

- [x] 1.1 Create the hexagonal package layout (`libs/cybercanon/{domain,application,adapters}`, `services/cybercanon/cli`, `tests/`) and verify `python -c "import cybercanon"` succeeds from a clean checkout
- [x] 1.2 Add `pyproject.toml` with dependencies (`pydantic`, `ruamel.yaml`, `typer`, `trimesh`, `pygltflib`) and dev dependencies (`pytest`, `pytest-cov`, `import-linter`, `ruff`); manage the environment with `uv`, commit `uv.lock`, and verify `uv sync --frozen` installs from the lock and `pytest --collect-only` runs
- [x] 1.2a Add the root `justfile` with the baseline recipes (`setup`, `check`, `test`, `lint`, `imports`, `complexity`, `spec`) and verify each runs from a clean checkout after `just setup`
- [x] 1.2b Make `just check` the single CI entry point and verify a test asserts the CI workflow invokes only that recipe, so a check in CI that is missing from the justfile fails the build
- [x] 1.3 Configure `import-linter` contracts — `domain ← application ← adapters`, inbound must not import outbound, and `libs/cybercanon/domain` must not import any third-party package (D10) — and verify `lint-imports` passes on the empty skeleton
- [x] 1.4 Add a CI workflow whose only step is `just check` (which runs `ruff`, `lint-imports`, `pytest` and `openspec validate --all --strict`), and verify it passes on the skeleton commit

## 2. Domain — the spec contract

- [x] 2.1 Model identity and lifecycle (`AssetId`, `Asset`, `Status` as the ordered enum `concept→approved→modeling→validated→in-engine`, owner fields) and verify unit tests reject a status outside the set
- [x] 2.2 Model the three authored blocks (`Concept`, `Design` with `sockets`, `Constraints` with `tri_budget`/`lods`/`texture`/`rig`/`collider`/`pivot`/`up_axis`/`unit_scale`/`naming`) as frozen value objects, each independently optional; verify a concept-only asset validates clean
- [x] 2.3 Model `Anchor2D` and `Anchor3D` (durable `part`, optional `bone`, hint `point`/`normal`, optional `camera`) and `Annotation` with `kind`, author, and exit state (`open | promoted | resolved`); verify tests assert no triangle-index or barycentric field exists on any anchor type
- [x] 2.4 Model the design state animation contract (`State` with name, optional `clip`, `loop`, `frame_rate`, `root_motion`, minimum duration, and an explicit unanimated declaration) and the `rig` additions (`max_bones`, expected skinning); verify a state declaring nothing checkable is rejected and one declaring `animated: false` validates clean
- [x] 2.5 Implement structural spec checks as pure functions — descending LODs, first LOD within `tri_budget`, duplicate `id` within a project, unknown status, and a state that resolves to no clip and is not declared unanimated — and verify each has a failing-case test naming the offending field

## 3. Domain — effective spec and validation rules

- [x] 3.1 Implement `MeshFacts` and `ClipFacts` as frozen value objects (triangles, objects, transforms_applied, unit_scale, up_axis, uv_sets, materials, empties, clips with name/frames/duration/frame_rate/root_motion/loop_closed, frame_rate, is_skinned, bone_count) carrying `source_format` and an `available` fact set (D1, D13); verify the domain package still passes `lint-imports` with zero third-party imports
- [x] 3.2 Implement the `EffectiveSpec` merge (project defaults ← asset constraints, asset wins per field) as one pure function (D3) and verify tests cover override, fallback, and neither-declared cases, including `rig.max_bones` and the clip naming convention
- [x] 3.3 Resolve `design.states` into `required_clips` inside that merge (D12) — explicit `clip` wins, otherwise expand the `{asset}`/`{state}` template — and verify the resolved list from a bare state list, from an explicit clip name, and that an unanimated state contributes nothing
- [x] 3.4 Implement `Violation` (stable `rule_id`, `severity`, `subject`, `observed`, `expected`, `message`), the three-way `RuleOutcome` (passed / violated / not evaluated) and `Report` carrying violations, not-evaluated rules with reasons, the export format, and an outcome failing if and only if an `error`-severity violation exists; verify a warnings-only report passes and a not-evaluated-only report passes while still listing them
- [x] 3.5 Implement the budget rules (`tri_budget.exceeded`, `lod.exceeded`) as pure functions over `MeshFacts` and verify over-budget, at-budget and under-budget cases from hand-built facts with no files on disk
- [x] 3.6 Implement the convention rules (`unit_scale.mismatch`, `up_axis.mismatch`, `transforms.unapplied`, `naming.pattern_mismatch`) and verify each names the specific offending object
- [x] 3.7 Implement the naming template expander (`SM_{asset}_LOD{n}` → matcher, D8) and verify matching and non-matching names, including LOD index substitution
- [x] 3.8 Implement `socket.missing` reading required sockets from the `design` block (not a separate engineering list) and verify the closed-loop case: two declared sockets, one present, exactly one violation naming the missing one, and that an extra socket is not a violation
- [x] 3.9 Implement `animation.clip_missing` reading `required_clips` from the resolved design states (not a separate engineering list) and verify the closed-loop case: two required clips, one present, exactly one violation naming the missing clip and its state, and that an extra clip is not a violation
- [x] 3.10 Implement the clip expectation rules (`animation.frame_rate_mismatch`, `animation.duration_too_short`, `animation.root_motion_missing`, `animation.loop_not_closed`) and verify each names the clip, the expectation and the observed value, from hand-built `ClipFacts`
- [x] 3.11 Implement `rig.bone_budget_exceeded` and `rig.not_skinned` and verify over-budget, at-budget, under-budget and rig-declared-but-unskinned cases from hand-built facts
- [x] 3.12 Implement the per-format capability matrix as one table `MeshFormat → frozenset[FactKind]` (D13) and verify a test asserting every `FactKind` is classified present or absent for every supported format, so adding a fact without classifying it fails the build
- [x] 3.13 Implement three-way rule dispatch — a rule whose required facts are unavailable yields `NotEvaluated(rule_id, missing_fact, reason)` — and verify with `MeshFacts` built with a deliberately narrow `available` set that the rule is neither reported as passing nor as violated
- [x] 3.14 Implement `format.unsuitable_for_asset` as an `error` violation when the spec declares clips, a rig or sockets and the export format cannot contain them, and verify the OBJ-with-clips case fails while OBJ for a static asset yields only not-evaluated rules
- [x] 3.15 Assemble the rule registry keyed by `rule_id`, each rule declaring the `FactKind`s it consumes and its default severity, and verify a test asserts every registered rule has a unique, stable identifier and a non-empty declared fact set

## 4. Application — ports and use cases

- [x] 4.1 Define the `SpecStore` port (load spec, discover governing spec by walking upward to the repository root, load project config) and verify a port-conformance test runs against the in-memory fake
- [x] 4.2 Define the `MeshInspector` port (path → `MeshFacts` including `source_format` and the `available` fact set, plus a handle for preview emission) and the `BlobStore` port (write preview, associate with asset and source export); verify both have in-memory fakes under `application/testing/`
- [x] 4.3 Implement the `validate_export` use case (discover spec → merge effective spec → extract facts → run rules → report) and verify it produces identical reports for identical `MeshFacts` regardless of source format
- [x] 4.4 Add optional preview emission inside `validate_export`, guarded so any preview failure is reported separately and cannot change the verdict (D7); verify a test where preview emission raises and the outcome stays passing
- [x] 4.5 Implement the `lint_spec` use case over one or many spec files and verify it reports structural violations with file path and field location, including a state that constrains nothing
- [x] 4.6 Verify at the use-case level that an unsupported export format is reported as such and never validated with assumed facts (test asserts a non-matrix format produces an operation failure, not a passing report)
- [x] 4.7 Implement the `compile_spec` use case emitting rules plus open annotations only, with effective values already merged; verify resolved and promoted annotations are excluded and that compiling the same input twice is byte-identical
- [x] 4.8 Implement the project-level briefing compilation (shared constraints and rules, no per-asset annotations) and verify no asset annotation appears in its output
- [x] 4.9 Verify offline behavior at the use-case level: a test asserting `validate_export` and `compile_spec` complete with every network-capable fake configured to raise

## 5. Adapters — outbound

- [x] 5.1 Implement `GitSpecStore`: parse `asset.yaml` with pydantic, read `schema_version` first and refuse only a newer major version with a message naming the required tool version (D6); verify round-trip parse tests and the newer-major refusal case
- [x] 5.2 Make unknown fields produce a `warning` naming the field and its location rather than a parse failure (D5) and verify a spec with an unrecognised field still validates its mesh
- [x] 5.3 Wire `ruamel.yaml` round-trip loading (D4) and verify a load-then-dump of a commented `asset.yaml` preserves comments and key order byte-for-byte
- [x] 5.4 Implement upward asset discovery bounded by the git root (D9) and verify discovery from an export path, from a nested path, and the no-spec-found case
- [ ] 5.5 Implement `TrimeshInspector` with per-format normalisation of unit scale and up axis for GLB/GLTF, FBX and OBJ, populating `available` from the capability matrix and never substituting a value for an unavailable fact; verify against real fixture files in an opt-in integration test suite, separate from the domain suite
- [ ] 5.6 Extract animation facts (clip names, frames/duration, frame rate, root motion, loop closure, skinning, bone count) for GLB/GLTF and FBX; verify against one skinned, animated fixture per format that clip names and durations match the authored source, and mark in the matrix any fact a format's extraction cannot be trusted for
- [x] 5.7 Verify OBJ behaviour end to end in the integration suite: an OBJ export of an animated asset reports `format.unsuitable_for_asset`, and an OBJ export of a static asset reports triangle, naming and material results plus not-evaluated entries for unit scale, up axis, sockets, rig and animation
- [ ] 5.8 Implement decimated Draco-compressed preview emission preserving object and attachment point names, and verify the preview has fewer triangles, a smaller file size, and retains a named part from the source
- [x] 5.9 Preserve animation clips and skinning through decimation — verify the preview carries the same clip names and durations and the same bone names as the source, and that an emitter unable to carry the clips reports a preview failure instead of writing a clipless preview
- [x] 5.10 Implement `FsBlobStore` writing previews with their asset id and source export recorded, and verify the association is readable back

## 6. Adapters — inbound CLI and wiring

- [x] 6.1 Build the composition root `adapters/wiring/container.py` (D11) and verify a test constructs the container with fakes and resolves every use case
- [x] 6.2 Implement `canon validate`, `canon compile` and `canon check` as thin Typer commands delegating to use cases, and verify no rule logic exists outside the domain (assert by import-linter plus a grep-based test)
- [x] 6.3 Implement the single exit-code seam — `0` clean, `1` error-severity violations, `2` operation could not run — and verify all three via subprocess tests, including the missing-file case naming the file
- [x] 6.4 Implement human-readable output where every violation names the asset, subject, observed and expected values; verify a triangle-budget message contains all four
- [x] 6.5 Print not-evaluated rules as their own section, never collapsed into a count, naming each rule and the reason its fact was unavailable; verify an OBJ run lists every suppressed rule by name
- [x] 6.6 Implement `--json` machine-readable mode writing only the structured result to stdout with diagnostics elsewhere, and verify stdout parses as JSON with nothing else on it, carrying violations, not-evaluated rules and the export format as distinct fields
- [x] 6.7 Implement changed-file invocation that validates only the owning assets and exits `0` when no file belongs to an asset; verify both cases via subprocess
- [x] 6.8 Verify no-credential operation: a subprocess test on a clean environment (no token, no config) completes a validation without prompting

## 7. Consumer-facing artifacts and acceptance

- [x] 7.1 Write the `.canon/project.yaml` schema for project defaults (naming pattern, clip naming convention, default frame rate, rig bone budget, up axis, unit scale, engine content root, per-rule severity, decimation settings) and verify defaults flow through `EffectiveSpec` into both validation and compiled output
- [x] 7.2 Provide a `.pre-commit-hooks.yaml` entry and document hook installation; verify the hook blocks a commit containing an over-budget export and allows a clean one
- [x] 7.3 Write `README.md` and a worked `characters/mech_scout` example — a skinned, animated asset whose `asset.yaml` declares sockets, states and a rig budget, plus its compiled `art-spec.md` — and verify the example validates and compiles via the CLI in CI
- [ ] 7.4 Run the acceptance test from the proposal: take one real asset end to end and record whether the 3D developer delivered without asking the artist a single clarifying question; log every question asked as a candidate missing schema field
- [ ] 7.5 Run that same asset's export through every supported format and compare coverage: verify each rule is reported as passed, violated or not evaluated in each format, and that no rule silently disappears from a report
- [x] 7.6 Run `openspec validate --all --strict` plus the full test suite and `lint-imports`, and confirm cognitive complexity per function is within the backend target of 15
