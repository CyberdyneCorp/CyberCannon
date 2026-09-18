# Design

## Context

Greenfield repository — nothing exists yet, so this change also lays the skeleton
every later change inherits: the hexagonal layout, the dependency rule, and the
test strategy. See `proposal.md — Why` for motivation and
`openspec/project.md` for the standing architectural decisions (git as source of
truth, agents read but never write constraints, the validator never requires
identity).

Two constraints shape everything below:

1. **Three inbound adapters will eventually drive the same validation** — the
   pre-commit hook, the Blender agent's MCP tool, and the web "Validate" button.
   Only the CLI ships now, but if the use case boundary is drawn wrongly today,
   the other two grow their own copies of the rules and the product acquires the
   exact bug it exists to prevent: *"it passed on my machine but the site says it
   failed."*
2. **The spec file is the product's real IP.** It will be read by contractors and
   language models years after this tool is replaced. It has to be boring,
   self-explanatory, and stable.

## Goals / Non-Goals

**Goals:**

- One validation implementation, reachable from any inbound adapter.
- A validator test suite that runs with zero files on disk, so mesh rules are
  cheap to add and impossible to break silently.
- A spec format whose evolution does not break older files.
- A repository layout and import contract that later changes extend rather than
  renegotiate.

**Non-Goals (design level, beyond the proposal's scope boundary):**

- No plugin or user-authored rule mechanism. Rules are code in this change; an
  extension point is speculative until a second project needs a different rule.
- No performance engineering. Correctness and testability first; a validation run
  is human-triggered and single-asset.
- No concurrency. Single process, one asset at a time.

## Decisions

### D1 — `MeshFacts` is the boundary: mesh *reading* is a port, mesh *rules* are domain

`MeshInspector` is a port returning a frozen, dumb value object:

```python
@dataclass(frozen=True)
class ClipFacts:
    name: str
    frames: int | None
    duration_s: float | None
    frame_rate: float | None
    has_root_motion: bool | None      # None = the format could not tell us
    loop_closed: bool | None

@dataclass(frozen=True)
class MeshFacts:
    source_format: MeshFormat         # GLB | GLTF | FBX | OBJ
    available: frozenset[FactKind]    # which fields below are meaningful
    triangles: int
    objects: tuple[str, ...]
    transforms_applied: bool
    unit_scale: float
    up_axis: str
    uv_sets: int
    materials: tuple[str, ...]
    empties: tuple[str, ...]          # attachment points / sockets
    clips: tuple[ClipFacts, ...]      # animation clips found in the export
    frame_rate: float | None          # the export's own frame rate
    is_skinned: bool
    bone_count: int
```

`available` is not decoration: a rule reads a field only after asserting its
`FactKind` is available, and the domain test suite builds `MeshFacts` with a
deliberately narrow `available` set to prove the not-evaluated path (D13).

The domain decides pass/fail against the effective spec. Nothing in
`libs/cybercanon/domain/` imports `trimesh`, `pygltflib`, or touches a file.

*Why:* it is the single decision that makes the whole validator testable — the
entire rule suite runs over hand-built `MeshFacts`, no fixtures, no binary assets
in git, no slow tests. It also makes the eventual `trimesh` → `bpy` swap a
one-adapter change. **Alternative rejected:** letting rules ask a mesh object
questions directly (`mesh.triangle_count()`), which reads more naturally and
makes every rule test require a real file and the extraction library.

*Consequence to accept:* every new rule needs its fact added to `MeshFacts`
first. That friction is the point — it keeps facts explicit and the port narrow.

### D2 — Rules are pure functions registered by identifier, not a class hierarchy

```python
Rule = Callable[[EffectiveSpec, MeshFacts], Iterable[Violation]]
```

Each rule is a small pure function with a stable `rule_id` (`tri_budget.exceeded`,
`naming.pattern_mismatch`, `socket.missing`, …), registered in one list. A rule
returns zero or more `Violation(rule_id, severity, subject, observed, expected,
message)`.

*Why:* the spec requires stable machine-readable rule identifiers and actionable
messages; a flat registry makes both trivially auditable — you can print the rule
inventory. Cognitive complexity per rule stays near 1–3, well under the ≤15
backend target. **Alternative rejected:** a `Rule` ABC with subclasses — more
ceremony, no added capability, and it invites shared mutable state between rules.

### D3 — `EffectiveSpec` is computed once, before any rule runs

Project defaults from `.canon/project.yaml` merge with the asset's own
`constraints`, asset wins per field. Rules receive only the merged result and
never see the merge.

*Why:* the merge is a single, testable pure function instead of a rule-by-rule
`asset.tri_budget or project.tri_budget` smear. It is also what lets the compiled
`art-spec.md` state effective values, as `spec-compilation` requires — the
compiler and the validator consume the identical merged object, so the briefing a
human reads and the contract the validator enforces cannot drift.

### D4 — Parse with pydantic, round-trip with `ruamel.yaml`

Two different jobs, two libraries. `pydantic` models define and validate the
schema (types, enums, cross-field checks such as descending LODs). `ruamel.yaml`
is used only when a future change needs to *write back* to `asset.yaml` while
preserving the artist's comments and key order.

*Why:* `asset.yaml` is a human-authored file living in a git diff. A writer that
reorders keys and eats comments produces unreviewable diffs and destroys trust in
the tool on first use. This change is read-only, but choosing the round-trip
loader now avoids a rewrite when annotation promotion lands. **Alternative
rejected:** `pyyaml` alone — smaller dependency, but it cannot preserve comments,
so the first write would churn every file.

### D5 — Unknown fields are reported, not rejected

An unrecognised field produces a `warning`-severity violation naming the field
and its location, not a parse failure.

*Why:* forward compatibility. A newer CyberCanon writes a field an older `canon`
binary does not know; the older binary must still validate the mesh rather than
refusing the file. The warning keeps typos visible without making version skew
fatal. **Alternative rejected:** pydantic's `extra="forbid"`, which turns any
version skew into a blocked commit — precisely the "tool becomes the enemy"
failure mode.

### D6 — `schema_version` in every spec file

`asset.yaml` carries a `schema_version`. The loader reads it first and refuses,
with a clear message naming the required tool version, only when the file's major
version is *newer* than the binary understands.

*Why:* cheap now, impossible to retrofit once files exist in repositories.

### D7 — Preview emission piggybacks on the validation read, behind `BlobStore`

`validate_export` is the use case; preview emission is an optional step within the
same run, guarded so its failure cannot alter the verdict (`asset-preview`
requires exactly this). The emitted GLB is Draco-compressed and decimated, and
goes through a `BlobStore` port — `FsBlobStore` now, `MinioBlobStore` when a
networked surface exists.

*Why:* the mesh is already in memory; re-reading a 200 MB export later to make a
preview is pure waste. **Alternative rejected:** a separate `canon preview`
command, which re-reads the file and lets preview and validation disagree about
which export they looked at.

*Decimation target:* a fixed fraction with a triangle ceiling, configurable per
project. Deliberately dumb — preview quality is not a hill worth tuning before a
viewer exists to reveal what is actually needed.

### D8 — Naming pattern is a template, not a regex, in the file

Specs and project config declare `naming: "SM_{asset}_LOD{n}"`. The domain expands
the template into a matcher internally.

*Why:* artists and designers author these files. A regex in `asset.yaml` is a
literacy tax on the people the tool most needs to keep. The template covers the
real cases; an escape hatch for a raw pattern can be added when something needs
it.

### D9 — Asset discovery walks upward, bounded by the repository root

Given any path, walk up looking for `asset.yaml`, stopping at the git root.
`SpecStore` owns this; the CLI does not do path arithmetic.

*Why:* `canon validate exports/SM_MechScout_LOD0.glb` has to just work, and the
same discovery is needed by the MCP server's `where_is` next change. Putting it in
the port means the next adapter inherits it.

### D10 — The validation path never imports the identity or network adapters

Enforced structurally with `import-linter`, not by convention:

```
domain  ←  application  ←  adapters
inbound adapters MUST NOT import outbound adapters
libs/cybercanon/domain MUST NOT import any third-party package
```

*Why:* `asset-validation` requires that validation completes with every remote
service unreachable. A test can be forgotten; a layering contract in CI cannot.
Result reporting, when it arrives, is a separate use case that is allowed to fail.

### D11 — Wire once in a composition root; the CLI stays a thin translator

`adapters/wiring/` builds a `Container`; `services/cybercanon/cli` maps arguments
in and a report out. Exit-code mapping lives in exactly one seam
(`0` clean, `1` error-severity violations, `2` operation could not run).

*Why:* the MCP server and FastAPI app are added by pointing at the same container.
That is what makes "one verdict across every surface" structural rather than
aspirational.

### D12 — Required clips are derived into `EffectiveSpec`, exactly like sockets

`design.states` is resolved, during the D3 merge, into
`required_clips: tuple[RequiredClip, ...]` where
`RequiredClip(state, clip_name, frame_rate, min_duration_s, root_motion, loop)`.
The clip name comes from the state's explicit `clip`, otherwise from expanding the
`clip_naming` template with the same expander D8 already builds for object names.
A state that resolves to neither a clip name nor `animated: false` is a
*spec-file* violation, caught by `lint_spec`, not a mesh violation.

*Why:* the socket loop works because `socket.missing` reads one derived list and
compares it to one fact list. Animation gets the same shape — `animation.clip_missing`
is the same three-line rule against `MeshFacts.clips` — so there is one place where
"what does design require" is computed and the compiler, the validator and the
lenses cannot disagree about it. It also makes `states` satisfy the golden rule:
before this, `states: [idle, walk, fire]` constrained nothing.

**Alternative rejected:** a separate `constraints.animations` list authored by
engineering. It is easier to implement — no template, no resolution step — and it
breaks the loop the product exists to close: design would declare a state, an
engineer would have to notice and restate it as a required clip, and the two lists
would drift on the first rename.

*Cost accepted:* an asset with states and no clip naming convention configured
becomes invalid until its author declares either a convention or `animated: false`
per state. That is a real adoption edit on existing files, and it is the price of
`states` meaning something. `lint_spec` names the state and the missing piece, so
the edit is mechanical.

### D13 — A per-format capability matrix, and a third rule outcome

One table in the domain maps `MeshFormat → frozenset[FactKind]`. The
`MeshInspector` adapter populates `MeshFacts.available` from it and never invents
a value for a fact its format cannot carry. Rule dispatch then has three outcomes
instead of two:

```python
RuleOutcome = Passed | Violated(Violation) | NotEvaluated(rule_id, missing_fact, reason)
```

`Report` carries `violations` and `not_evaluated` as separate lists, and the
overall outcome still fails if and only if an `error`-severity violation exists.
Separately, a *requirement* the format can never contain — clips, a skeleton or
empties for `OBJ` — is an ordinary `error` violation
(`format.unsuitable_for_asset`), because that is an export mistake with an obvious
fix, not an unknown.

The distinction is deliberate and is the whole decision: **cannot observe** →
not evaluated; **cannot contain** → unsuitable format. `OBJ` records no unit
scale, so an `OBJ` file may well be correctly scaled and we must not claim
otherwise. `OBJ` cannot hold an animation clip, so an asset requiring one can
never be satisfied by an `OBJ` export and saying so early is strictly kinder than
saying it at integration.

*Why now:* unstated, the rules silently pass on `OBJ` — a green report on a file
where the rig, bone budget, sockets, unit scale and every animation rule were
never run. A validator that lies about its coverage is worse than one that refuses
the format, because the team stops looking.

**Alternative rejected:** reject `OBJ` outright and support only `GLB`/`GLTF` and
`FBX`. Simpler — no matrix, no third outcome, every rule always runs — and it
throws away the real case where `OBJ` is the right format: static props, where
triangle budget, object naming and material rules are the entire contract and all
three are evaluable. It also does not actually solve the problem, because `FBX`
extraction is itself uneven (see the risks below) and the same silent-pass
question returns one format later.

*Cost accepted:* three outcomes propagate everywhere a report is rendered — CLI
prose, `--json`, and every later surface — and every rule must declare which facts
it consumes. The matrix is also a maintenance item: adding a fact means revisiting
each format's row, and a wrong row produces a *wrong* not-evaluated, which is
quieter than a wrong violation. Mitigated by keeping the matrix a single table
with a test asserting every `FactKind` appears in every format's row as present or
absent, so adding a fact without classifying it fails the build.

## Risks / Trade-offs

- **The schema is wrong in a way only real use reveals** → Ship `schema_version`
  and tolerant unknown-field handling (D5, D6) so the format can move, and run the
  proposal's acceptance test — one real asset end to end — before building any
  UI on top. If the modeller had to ask the artist a clarifying question, a field
  is missing, and that is cheap to learn now and expensive to learn after the
  viewer exists.
- **`trimesh` reports facts inconsistently across FBX and GLTF** (unit scale and
  up axis are the usual offenders, and FBX support is weaker than GLTF) → Keep
  extraction entirely inside the adapter with per-format normalisation and its own
  integration tests on real files, separate from the domain suite. If FBX proves
  unreliable, the fallback is to require GLB for validation and document it, which
  costs a workflow note rather than a redesign.
- **Rules that are strict but wrong block commits and turn the team against the
  tool** → Default new rules to `warning`; promote to `error` only once the team
  has seen the noise. Severity is per rule and configurable per project.
- **Template-based naming (D8) cannot express a convention someone already uses**
  → Accepted for now; the regex escape hatch is additive when a real case appears.
- **Draco compression adds a native dependency that can fail to install on some
  machines** → Preview emission is optional and non-fatal by construction (D7), so
  a machine that cannot produce previews can still validate and commit.
- **Animation fact extraction differs sharply between GLTF and FBX** — clip
  duration, frame rate and root motion are explicit in glTF and inconsistent in
  FBX, and `trimesh` is weakest exactly there → Per-format normalisation stays in
  the adapter with its own integration fixtures (one skinned, animated asset per
  format). Where a format's extraction cannot be trusted for a fact, the honest
  move is to mark that fact unavailable in the matrix so the rule reports *not
  evaluated* rather than a fabricated mismatch. That is the matrix earning its
  keep: it doubles as the record of what we can actually read today.
- **A wrong matrix row silently suppresses a real rule** — a fact marked
  unavailable that the format does carry means a rule that should have failed is
  reported as not evaluated instead → Not-evaluated rules are printed in every
  rendering, never collapsed into a summary count, so suppression is visible on
  every run rather than discoverable only by reading the table. The acceptance run
  (task 7.4) validates the same asset exported to each supported format and
  compares coverage.
- **Decimation drops skinning or clips to hit its triangle target** — a preview
  that loads but cannot animate would send the 3D viewer back to the working
  export, defeating the point of previews → `asset-preview` makes this a preview
  *failure* rather than a silently degraded preview, and the emitter verifies clip
  names, durations and bone names against the source before writing.
- **Teams already exporting animated assets as OBJ will see a hard error on day
  one** → Intended. The message names the declared requirement and the format, and
  the fix is a re-export, not a spec change. The alternative is a green report on
  an unchecked file.
- **Cost of the boundary:** adding a rule that needs a new fact touches the port,
  the adapter, the fake, the format matrix and the domain — five files for one
  rule. Accepted deliberately in exchange for a rule suite that runs in
  milliseconds with no binary fixtures in git.

## Migration Plan

Not applicable — greenfield, no existing data and no consumers. Adoption in a game
repository is additive: add `asset.yaml` files, optionally `.canon/project.yaml`,
and a pre-commit hook entry. A repository with no `asset.yaml` is unaffected, and
the hook exits `0` when no touched file belongs to an asset. Rollback is removing
the hook.

## Open Questions

- **Default decimation ratio and triangle ceiling for previews.** Answerable when
  the 3D viewer exists and shows what is actually needed; it is a configuration
  value, so it changes no spec, no approach and no task.
- **Which rules ship as `error` versus `warning` by default.** Tunable per
  project after the first real asset run; the severity mechanism itself is
  specified and built in this change.
- **Whether loop closure should be an `error` rather than a `warning`.** Needs the
  3D viewer to show what a failed loop actually looks like in motion; it is a
  severity value, so it changes no spec, no approach and no task.
- **Frame-rate comparison tolerance.** Whether `29.97` satisfies a declared `30`
  is an engine-dependent question best answered by the first real Unreal or Unity
  import; until then the comparison is exact and the rule is a `warning`.
