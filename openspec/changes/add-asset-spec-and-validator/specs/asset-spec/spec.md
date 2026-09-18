# Spec Delta

## Purpose

Defines `asset.yaml`, the single versioned contract per asset that states what it
looks like (art), what it does (design) and what it must respect technically
(engineering), stored in the game repository next to the asset so git provides
history, diff, blame and review.

## ADDED Requirements

### Requirement: Spec file location and source of truth

An asset's specification SHALL be a file named `asset.yaml` stored in the game
repository, in the same directory as the asset it describes. The repository SHALL
be the authoritative source of an asset's specification. Any index, cache or
database derived from specification files SHALL be reconstructible by re-reading
the repository, and the system SHALL NOT require such a derived store to read,
validate or compile a specification.

#### Scenario: Spec read directly from a working copy
- **GIVEN** a game repository containing `characters/mech_scout/asset.yaml`
- **WHEN** the system is asked for the specification of `mech_scout`
- **THEN** it SHALL read the file from the working copy
- **AND** it SHALL NOT require any database, service or network connection

#### Scenario: Derived index is disposable
- **GIVEN** any derived index of specifications exists
- **WHEN** that index is deleted
- **THEN** re-scanning the repository SHALL restore it completely
- **AND** no specification data SHALL be lost

### Requirement: Asset identity and aliases

A specification SHALL declare a stable `id` unique within its project, a
human-readable `name`, and MAY declare `aliases`: a list of alternative
human-written terms for the same asset. The `id` SHALL be the identifier used by
every other surface to refer to the asset and SHALL NOT change when `name`
changes.

#### Scenario: Duplicate id within a project
- **GIVEN** two specification files in the same project declare `id: mech_scout`
- **WHEN** the project is validated
- **THEN** the system SHALL report a violation naming both file paths

#### Scenario: Renaming does not break references
- **GIVEN** an asset with `id: mech_scout` and `name: "Scout Mech"`
- **WHEN** `name` is changed to `"Recon Walker"`
- **THEN** the `id` SHALL remain `mech_scout`
- **AND** existing references to `mech_scout` SHALL continue to resolve

### Requirement: Three authored blocks with distinct authorship

A specification SHALL support three authored blocks — `concept` (authored by
art), `design` (authored by game design) and `constraints` (authored by
engineering) — and each block SHALL be independently optional so that an asset
can exist with only a concept.

#### Scenario: Concept-only asset is valid
- **GIVEN** a specification declaring identity and a `concept` block only
- **WHEN** the specification file is validated
- **THEN** it SHALL be reported as a valid specification
- **AND** the absence of `design` and `constraints` SHALL NOT be a violation

### Requirement: Design fields must constrain or be checkable

Every field defined in the `design` block SHALL either constrain art, constrain
code, or be mechanically checkable by the validator. The `design` block SHALL
support at minimum: `role`, `read_distance_m`, `silhouette_priority`, `states`,
`scale_ref`, `team_color_regions` and `sockets`, where each socket declares a
`name` and a `purpose`. Free-form prose that constrains nothing SHALL NOT be
introduced as a design field.

#### Scenario: Declared socket becomes an export gate
- **GIVEN** a specification whose `design.sockets` declares `SOCKET_muzzle_l`
- **WHEN** an export for that asset is validated
- **THEN** the absence of an attachment point named `SOCKET_muzzle_l` SHALL be
  reported as a violation

### Requirement: Design states declare an animation contract

Every entry in `design.states` SHALL resolve either to a **required animation
clip** or to an explicit declaration that the state has no animation. A state
entry SHALL carry a state name, and MAY additionally declare an explicit `clip`
name, `loop`, `frame_rate`, `root_motion`, and a minimum duration expressed in
seconds or in frames. A state that resolves to no required clip and does not
declare itself unanimated SHALL be reported as a violation of the specification
file naming that state, because such a state constrains neither art nor code and
cannot be checked.

#### Scenario: A named state becomes an export gate
- **GIVEN** a specification whose `design.states` lists `fire`
- **AND** a clip naming convention resolving that state to `A_mech_scout_fire`
- **WHEN** an export for that asset is validated
- **THEN** the absence of an animation clip named `A_mech_scout_fire` SHALL be
  reported as a violation

#### Scenario: A state with no animation is declared explicitly
- **GIVEN** a state `destroyed` declaring that it has no animation
- **WHEN** the specification file is validated
- **THEN** it SHALL be reported as valid
- **AND** no animation clip SHALL be required for that state

#### Scenario: A state that constrains nothing is rejected
- **GIVEN** a state that names no clip, resolves to no clip through any
  convention, and does not declare itself unanimated
- **WHEN** the specification file is validated
- **THEN** a violation SHALL be reported naming that state

### Requirement: Animation clip names follow a declared convention

A project SHALL be able to declare a clip naming convention as a template with
`{asset}` and `{state}` placeholders, such as `A_{asset}_{state}`, and an asset
SHALL be able to override it. A state's explicit `clip` name SHALL take
precedence over the expanded template. The convention SHALL be authored as a
template rather than as a regular expression, and the required clip name for a
state SHALL be derivable from the specification alone, with no export present.

#### Scenario: Template expands to the required clip name
- **GIVEN** a clip naming convention of `A_{asset}_{state}`
- **AND** an asset `mech_scout` with a state `walk`
- **WHEN** the required clips are resolved
- **THEN** the required clip name SHALL be `A_mech_scout_walk`

#### Scenario: An explicit clip name wins over the convention
- **GIVEN** a clip naming convention of `A_{asset}_{state}`
- **AND** a state `walk` declaring `clip: Locomotion_Walk_Fwd`
- **WHEN** the required clips are resolved
- **THEN** the required clip name SHALL be `Locomotion_Walk_Fwd`
- **AND** `A_mech_scout_walk` SHALL NOT be required

### Requirement: Engineering constraints block

The `constraints` block SHALL support at minimum: `tri_budget`, `lods` as an
ordered list of triangle counts, `texture` (size, sets, channels), `rig`
(skeleton, `max_bones`, and whether the mesh is expected to be skinned),
`animation` (a default `frame_rate` and the clip naming convention), `collider`,
`pivot`, `up_axis`, `unit_scale` and a `naming` pattern. A project MAY declare defaults for these in a project-level
configuration file, and an asset's own `constraints` SHALL take precedence over
the project default for any field it declares.

#### Scenario: Asset constraint overrides project default
- **GIVEN** a project default of `tri_budget: 8000`
- **AND** an asset declaring `tri_budget: 12000`
- **WHEN** an export for that asset is validated
- **THEN** the effective budget SHALL be 12000

#### Scenario: Project default applies when asset is silent
- **GIVEN** a project default of `up_axis: Z`
- **AND** an asset declaring no `up_axis`
- **WHEN** an export for that asset is validated
- **THEN** the effective up axis SHALL be `Z`

#### Scenario: Bone budget inherited from the project
- **GIVEN** a project default of `rig.max_bones: 96`
- **AND** an asset declaring a `rig` without `max_bones`
- **WHEN** an export for that asset is validated
- **THEN** the effective bone budget SHALL be 96

### Requirement: Status lifecycle

A specification SHALL declare a `status` from the ordered set
`concept`, `approved`, `modeling`, `validated`, `in-engine`. A value outside this
set SHALL be reported as a violation of the specification file.

#### Scenario: Unknown status rejected
- **WHEN** a specification declares `status: wip`
- **THEN** the system SHALL report a violation naming the allowed values

### Requirement: Tri-disciplinary ownership

A specification SHALL support three independent owner fields — `owner_art`,
`owner_design` and `owner_code` — each identifying an actor. Ownership SHALL be
per discipline; the format SHALL NOT assume a single owner per asset.

#### Scenario: Owners are independent
- **GIVEN** a specification declaring `owner_art` and `owner_code` but no `owner_design`
- **WHEN** the specification file is validated
- **THEN** it SHALL be reported as valid
- **AND** the missing `owner_design` SHALL be reported at most as a warning

### Requirement: Links to related artifacts

A specification SHALL support a `links` block recording where the asset's related
artifacts live, including at minimum the authoring source file, the engine
content path, and MAY include a discussion thread URL and a long-form design
document URL. Link values SHALL be stored verbatim; the system SHALL NOT be
required to resolve or fetch them in order to read the specification.

#### Scenario: Unreachable link does not invalidate the spec
- **GIVEN** a specification whose `links.discussion` points to an unreachable URL
- **WHEN** the specification file is validated
- **THEN** it SHALL be reported as valid
- **AND** no network request SHALL be made

### Requirement: Annotation entries with durable dual anchors

A specification SHALL support an `annotations` list. Each annotation SHALL carry
an `id` unique within the asset, an author, a `kind` from
`art-direction | technical | design`, a `text`, a resolution state, and a
`target` anchor. An anchor SHALL be one of two forms:

- a **2D anchor** naming a concept `view` and a normalized coordinate within it;
- a **3D anchor** whose durable key is a named mesh `part`, optionally a `bone`,
  with `point` and `normal` recorded in object space as positioning hints only,
  and an optional `camera` (position, target, field of view).

For a 3D anchor, the named part SHALL be the identifying key and the point and
normal SHALL NOT be treated as identity. The format SHALL NOT store triangle
indices or barycentric coordinates as an anchor, because those do not survive
re-export of the mesh.

#### Scenario: Anchor survives a remesh
- **GIVEN** an annotation anchored to part `SM_MechScout_Shoulder_L`
- **WHEN** the mesh is retopologised and re-exported with that part still present
- **THEN** the annotation SHALL still resolve to that part
- **AND** its recorded point and normal SHALL be treated as hints, not identity

#### Scenario: Missing part yields an orphan, not a wrong placement
- **GIVEN** an annotation anchored to part `SM_MechScout_Shoulder_L`
- **WHEN** that part is renamed or removed from the export
- **THEN** the annotation SHALL be reported as orphaned
- **AND** the system SHALL NOT silently relocate it to another part

### Requirement: Annotations have exactly two exits

Every annotation SHALL end in exactly one of two states: **promoted**, meaning
its content was moved into `constraints` or `concept.silhouette_rules` as a
durable rule and the annotation is retired; or **resolved**, meaning it was a
specific transient issue that has been addressed. The specification format SHALL
record which exit an annotation took. Retired and resolved annotations SHALL
remain removable from the file, with their history preserved by version control
rather than by accumulation in the file.

#### Scenario: Promotion retires the annotation
- **GIVEN** an open annotation stating that lens glow is always emissive
- **WHEN** it is promoted to a rule
- **THEN** the rule SHALL appear in the asset's durable rules
- **AND** the annotation SHALL be marked promoted and SHALL NOT remain open

#### Scenario: Resolution does not become permanent context
- **GIVEN** an annotation reporting that an arm clips at 45 degrees
- **WHEN** it is resolved
- **THEN** it SHALL be marked resolved
- **AND** it SHALL NOT be presented as a standing rule of the asset

### Requirement: Specification file validity is checkable offline

The system SHALL be able to report whether a specification file is structurally
valid — parseable, with known fields, required identity present, values of the
declared types, and cross-field consistency such as LOD counts being descending
and the first LOD not exceeding `tri_budget` — using only the file and the
project configuration, with no identity, no network and no derived store.

#### Scenario: Ascending LOD list rejected
- **WHEN** a specification declares `lods: [2000, 6000, 12000]`
- **THEN** the system SHALL report a violation stating LOD triangle counts must
  be descending

#### Scenario: Unknown field reported
- **WHEN** a specification declares a field not defined by the schema
- **THEN** the system SHALL report it, naming the field and its location in the file
