# CyberCanon

**One verifiable contract per asset.** What an asset *looks like* (art), what it
*does* (design) and what it *must respect technically* (engineering) are written
down once, in `asset.yaml`, next to the asset in the game repository — and a
validator enforces the technical half before anyone spends three days modelling.

```
$ canon validate characters/mech_scout/exports/SM_mech_scout_LOD0.glb
characters/mech_scout/exports/SM_mech_scout_LOD0.glb
  asset mech_scout | spec characters/mech_scout/asset.yaml | GLB
  1 violation (1 error, 0 warning)
    error  socket.missing  asset mech_scout  subject SOCKET_muzzle_l  observed absent  expected an attachment point named SOCKET_muzzle_l
      mech_scout: design declares socket 'SOCKET_muzzle_l' and the export contains no attachment point of that name

FAILING
$ echo $?
1
```

Three properties hold everywhere, and everything else follows from them:

- **Git is the source of truth.** `asset.yaml` lives in the game repository.
  There is nothing to sync, and `git diff`, `git blame` and pull-request review
  are the version history of your art direction.
- **The validator never requires identity.** No login, no token, no network. A
  tool an artist cannot use off-VPN becomes the enemy on its first bad day.
- **One core, three surfaces.** The pre-commit hook, the MCP tool a Blender
  agent calls and the web "Validate" button run the *same* use case, so
  "it passed on my machine but the site says it failed" cannot happen.

---

## Install

```sh
uv tool install cybercanon     # or: uv sync, inside this repository
canon --help
```

## The four commands

| Command | What it does |
|---|---|
| `canon validate EXPORT...` | Validate exports against the specification that governs them. |
| `canon check [PATH]` | Check that the specification files are themselves valid. |
| `canon compile SPEC` | Compile `asset.yaml` into the readable `art-spec.md`. |
| `canon changed FILE...` | Validate only the assets a list of changed files belongs to — the pre-commit entry point. |

You never name the specification: given any path, `canon` walks upward to the
governing `asset.yaml`, bounded by the repository root.

**Exit codes are stable and scriptable:**

| Code | Meaning |
|---|---|
| `0` | The operation ran and produced no `error`-severity violation. |
| `1` | The operation ran and produced at least one `error`-severity violation. |
| `2` | The operation could not run at all — a missing export, an unreadable file, a format outside the matrix, or no `asset.yaml` above the path. |

`2` is deliberately distinct from `1`: *"your mesh is wrong"* and *"I could not
look at your mesh"* are different sentences, and a hook that conflated them would
send an artist to fix an export nobody read.

**`--json` on any command** writes the structured result to standard output and
nothing else; prose, diagnostics and failures go to standard error. Violations,
not-evaluated rules and the export format are distinct fields, because a script
that confuses *failed* with *never ran* is worse than one that has neither.

## Three outcomes, not two

A rule **passed**, was **violated**, or **could not be evaluated** because the
export's format does not record the fact it reads. OBJ carries no unit scale, so
an OBJ export may well be correctly scaled and `canon` will not claim otherwise:

```
$ canon validate props/crate/exports/SM_crate_LOD0.obj
props/crate/exports/SM_crate_LOD0.obj
  asset crate | spec props/crate/asset.yaml | OBJ
  no violations
  not evaluated (11) — the export's format does not record the fact each rule reads
    unit_scale.mismatch  needs unit scale  — OBJ carries no unit scale
    up_axis.mismatch  needs up axis  — OBJ carries no up axis
    socket.missing  needs attachment points  — OBJ carries no attachment points
    ...
  4 rules passed
```

Every suppressed rule is printed **by name**, never as a count — that listing is
the only place a wrong capability row is ever visible.

A format that *cannot contain* what the specification requires is a different
thing entirely: an animated asset exported as OBJ is an ordinary `error`
(`format.unsuitable_for_asset`), and the fix is a re-export.

## Use it as a pre-commit hook

```yaml
# .pre-commit-config.yaml, in the game repository
repos:
  - repo: https://github.com/cyberdynecorp/cybercanon
    rev: v0.1.0
    hooks:
      - id: canon
```

```sh
pre-commit install
```

The hook receives the staged files and validates only the assets they belong to.
A commit that touches no asset exits `0` without doing any work, so a repository
that has not adopted `asset.yaml` yet is unaffected. Adoption is additive;
rollback is deleting the hook.

## The worked example

[`examples/ronin/`](examples/ronin) is a complete, validating game repository:

```
examples/ronin/
  .canon/project.yaml                        project defaults and standing rules
  characters/mech_scout/asset.yaml           the contract
  characters/mech_scout/art-spec.md          the compiled briefing (derived)
```

`mech_scout` is skinned and animated, declares an attachment point, two design
states and a rig budget, and every rule it can be measured against passes. Its
`art-spec.md` is what a contractor, a new hire or a language model is handed:
rules and currently open issues, with effective values already merged — never a
paraphrase, never a resolved thread.

The closed loop the whole system exists for is visible in it:

> design declares `SOCKET_muzzle_l` → art places an empty with that name →
> `socket.missing` rejects the export without it → code never discovers at
> integration time that the muzzle VFX has nothing to attach to.

## `asset.yaml`

```yaml
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling          # concept -> approved -> modeling -> validated -> in-engine

concept:                  # authored by art
  views: [concept/mech_scout_front.png]
  silhouette_rules: ["One asymmetric shoulder reads as the front at 25 m."]

design:                   # authored by design
  role: fast recon walker
  read_distance_m: 25
  sockets:
    - name: SOCKET_muzzle_l
      purpose: muzzle flash origin
  states:
    - { name: walk, loop: true, root_motion: true }
    - { name: fire, loop: false }

constraints:              # authored by engineering
  tri_budget: 12000
  lods: [12000, 6000, 2000]
  rig: { skeleton: SK_MechScout, skinned: true }
```

**The golden rule for the `design` block:** every field either constrains art,
constrains code, or is checkable by the validator. A field that does none of the
three is a wiki page, not a spec field. `states` earns its place because it
resolves into *required clips* the export must contain.

**An unknown field is a warning, not a failure.** A newer CyberCanon writing a
field your binary has never heard of must not block your commit. Only a *newer
major* `schema_version` is refused, and the message names the version you need.

## `.canon/project.yaml`

Project defaults, merged field by field with each asset's own `constraints` —
the asset wins wherever it declares something. The merge happens once, before
any rule runs, and the compiled `art-spec.md` states the same merged values the
validator enforces, so the briefing and the contract cannot drift.

```yaml
schema_version: 1
name: Ronin
engine_content_root: Content/Ronin        # where the imported asset lives
golden_rules:
  - The silhouette reads at 25 m before any detail does.

defaults:                                 # an ordinary `constraints` block
  up_axis: Y
  unit_scale: 1.0
  pivot: feet centre
  naming: "SM_{asset}_LOD{n}"             # a template, never a regex
  animation:
    frame_rate: 30
    clip_naming: "A_{asset}_{state}"      # how a state resolves to a clip name
  rig:
    max_bones: 64

severity:                                 # per rule, per project
  naming.pattern_mismatch: warning

preview:                                  # decimation targets
  ratio: 0.25
  ceiling: 20000
```

| Key | Meaning |
|---|---|
| `defaults.naming` | Object naming template. `{asset}` and `{n}` (the LOD index) are expanded. |
| `defaults.animation.clip_naming` | How a design state resolves to a clip name. Without it, a state must declare `clip:` or `animated: false`. |
| `defaults.animation.frame_rate` | The rate clips are expected at, unless a state overrides it. |
| `defaults.rig.max_bones` | The bone budget `rig.bone_budget_exceeded` enforces. |
| `defaults.up_axis`, `defaults.unit_scale` | The export conventions, checked wherever the format records them. |
| `engine_content_root` | Where the engine keeps imported content, for the people who have to find it. |
| `severity.<rule_id>` | Lower a noisy rule to `warning`, or promote it to `error`, without editing the rule. |
| `preview.ratio`, `preview.ceiling` | What preview decimation aims for. A preview never changes a verdict. |

A repository with no `.canon/project.yaml` works: every asset-level declaration
still applies.

## Developing CyberCanon

There is exactly one way to run any operation, and it is a `just` recipe:

```sh
just setup     # uv sync from the committed lock file
just check     # everything CI runs, in CI's order — and nothing else
just test      # unit + BDD + conformance + integration, with both traceability gates
just lint      # ruff
just imports   # the layering contract: domain <- application <- adapters
just spec      # openspec validate --all --strict
```

`just check` is the contract: a green local run means a green pipeline. The
architecture, the decisions behind it and the specifications live in
[`openspec/`](openspec) — start with
[`openspec/project.md`](openspec/project.md).
