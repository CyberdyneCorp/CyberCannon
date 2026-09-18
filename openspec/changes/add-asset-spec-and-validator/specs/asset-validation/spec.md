# Spec Delta

## Purpose

Evaluates an exported mesh against its asset's constraints and design
declarations, turning budgets, conventions, declared sockets and declared
animation clips into a mechanically enforced gate that produces the same verdict
wherever it is run, and that states plainly which rules its export format left
unevaluated instead of passing them in silence.

## ADDED Requirements

### Requirement: Validation is a pure decision over extracted mesh facts

Validation SHALL be performed by evaluating rules against a fixed set of facts
extracted from an exported mesh: triangle count, object names, whether transforms
are applied, unit scale, up axis, UV set count, material names, attachment point
(empty) names, animation clip names with their durations or frame counts, the
export's frame rate, whether the mesh is skinned, and its bone count. Every fact
SHALL additionally be marked as available or unavailable for the export
examined, so that a fact the export's format cannot carry is never presented as
a default value. The pass/fail decision SHALL depend only on those facts and the
effective specification, and SHALL NOT depend on the file format, the extraction
library, or the surface that requested it.

#### Scenario: Same facts produce the same verdict
- **GIVEN** two exports in different file formats that yield identical mesh facts
- **WHEN** both are validated against the same specification
- **THEN** the resulting violations SHALL be identical

#### Scenario: An unavailable fact is not defaulted
- **GIVEN** an export in a format that records no bone count
- **WHEN** facts are extracted from it
- **THEN** the bone count SHALL be marked unavailable
- **AND** it SHALL NOT be reported as zero or as any other substitute value

### Requirement: One verdict across every surface

A given export and specification SHALL produce the same verdict regardless of
whether validation was requested from the command line, from an automated agent,
or from an application user interface. The system SHALL NOT contain more than one
implementation of the validation rules.

#### Scenario: Command line and application agree
- **GIVEN** an export that fails its triangle budget
- **WHEN** it is validated from the command line and again from any other surface
- **THEN** both SHALL report the same violations with the same severities

### Requirement: Validation requires no identity and no network

Validation SHALL complete using only local files and the project configuration.
It SHALL NOT require authentication, an access token, or any network call, and
SHALL NOT fail because an identity provider or remote service is unavailable.

#### Scenario: Validation succeeds while services are down
- **GIVEN** the identity provider and all remote services are unreachable
- **WHEN** an export is validated locally
- **THEN** validation SHALL complete and report its violations normally

#### Scenario: Reporting a result is separable and non-blocking
- **GIVEN** a configured destination for reporting validation results
- **WHEN** that destination is unreachable
- **THEN** the validation verdict SHALL still be produced and returned
- **AND** the failure to report SHALL NOT change the verdict

### Requirement: Budget rules

The system SHALL report a violation when an export's triangle count exceeds the
effective `tri_budget`, and when a supplied LOD's triangle count exceeds the
budget declared for that LOD level. Each violation SHALL state the observed
value, the allowed value, and the asset it belongs to.

#### Scenario: Over budget
- **GIVEN** an effective `tri_budget` of 12000
- **WHEN** an export containing 14310 triangles is validated
- **THEN** a violation SHALL be reported stating observed 14310 and allowed 12000

#### Scenario: Within budget
- **GIVEN** an effective `tri_budget` of 12000
- **WHEN** an export containing 11840 triangles is validated
- **THEN** no triangle budget violation SHALL be reported

### Requirement: Mechanical convention rules

The system SHALL report a violation when an export's unit scale differs from the
effective `unit_scale`, when its up axis differs from the effective `up_axis`,
when object transforms have not been applied, or when an object name does not
match the effective `naming` pattern. Each violation SHALL name the specific
object or property at fault.

#### Scenario: Unapplied transforms
- **WHEN** an export contains an object whose transforms are not applied
- **THEN** a violation SHALL be reported naming that object

#### Scenario: Naming pattern mismatch
- **GIVEN** an effective naming pattern of `SM_{asset}_LOD{n}`
- **WHEN** an export contains an object named `mesh_final_v2`
- **THEN** a violation SHALL be reported naming that object and the expected pattern

### Requirement: Declared sockets are enforced

When an asset's `design` block declares sockets, the system SHALL report a
violation for each declared socket that has no corresponding attachment point in
the export. This SHALL be evaluated from the design declaration, not from a
separate engineering list, so that a design requirement becomes an export gate
without engineering restating it.

#### Scenario: Missing socket blocks the export
- **GIVEN** `design.sockets` declares `SOCKET_muzzle_l` and `SOCKET_jet_r`
- **WHEN** an export containing only an attachment point named `SOCKET_jet_r` is validated
- **THEN** exactly one violation SHALL be reported, naming `SOCKET_muzzle_l`

#### Scenario: Extra attachment points are not violations
- **GIVEN** `design.sockets` declares `SOCKET_muzzle_l`
- **WHEN** an export contains `SOCKET_muzzle_l` and an additional `SOCKET_spare`
- **THEN** no socket violation SHALL be reported

### Requirement: Declared animation clips are enforced

When an asset's `design` states resolve to required animation clips, the system
SHALL report a violation for each required clip that has no clip of that name in
the export, naming the missing clip and the state that required it. Clips present
in the export that no state requires SHALL NOT be reported as violations. This
SHALL be evaluated from the design declaration, not from a separate engineering
list, so that a declared state becomes an export gate without engineering
restating it.

#### Scenario: Missing clip blocks the export
- **GIVEN** an asset whose states resolve to required clips `A_mech_scout_walk`
  and `A_mech_scout_fire`
- **WHEN** an export containing only a clip named `A_mech_scout_walk` is validated
- **THEN** exactly one violation SHALL be reported, naming `A_mech_scout_fire`
- **AND** the violation SHALL name the state that required it

#### Scenario: Extra clips are not violations
- **GIVEN** an asset whose only required clip is `A_mech_scout_walk`
- **WHEN** an export contains `A_mech_scout_walk` and an additional
  `A_mech_scout_test`
- **THEN** no animation clip violation SHALL be reported

#### Scenario: An asset requiring no clips is unaffected
- **GIVEN** an asset whose states all declare themselves unanimated
- **WHEN** an export containing no animation clips is validated
- **THEN** no animation clip violation SHALL be reported

### Requirement: Declared clip expectations are enforced

When a state declares a `frame_rate`, a minimum duration, `root_motion` or
`loop`, and the corresponding facts are available for the export, the system
SHALL report a violation when the matching clip does not meet the declaration.
Each such violation SHALL name the clip, the expectation and the observed value.

#### Scenario: Frame rate mismatch
- **GIVEN** a state declaring `frame_rate: 30`
- **WHEN** its clip is exported at 24 frames per second
- **THEN** a violation SHALL be reported naming the clip, the expected 30 and the
  observed 24

#### Scenario: Missing root motion
- **GIVEN** a state `walk` declaring `root_motion: true`
- **WHEN** its clip animates no translation of the root
- **THEN** a violation SHALL be reported naming the clip and the expectation

#### Scenario: Clip shorter than the declared minimum
- **GIVEN** a state declaring a minimum duration of 1.0 second
- **WHEN** its clip is 0.4 seconds long
- **THEN** a violation SHALL be reported stating observed 0.4 and the declared
  minimum 1.0

### Requirement: Rig budget and skinning are enforced

The system SHALL report a violation when the export's bone count exceeds the
effective `rig.max_bones`, stating the observed and allowed counts. When an asset
declares a rig and the export is not skinned, the system SHALL report a violation
naming the asset and the declared skeleton. A bone count at or below the budget
SHALL produce no violation.

#### Scenario: Over the bone budget
- **GIVEN** an effective `rig.max_bones` of 96
- **WHEN** an export whose skeleton has 118 bones is validated
- **THEN** a violation SHALL be reported stating observed 118 and allowed 96

#### Scenario: Within the bone budget
- **GIVEN** an effective `rig.max_bones` of 96
- **WHEN** an export whose skeleton has 74 bones is validated
- **THEN** no bone budget violation SHALL be reported

#### Scenario: Rig declared but export is not skinned
- **GIVEN** an asset declaring a rig
- **WHEN** an export containing no skinning is validated
- **THEN** a violation SHALL be reported naming the asset and the declared skeleton

### Requirement: Per-format fact availability matrix

The system SHALL define, in a single place, which of the facts listed above each
supported export format can yield, and that matrix SHALL be the only basis for
deciding whether a rule can be evaluated for a given export. At minimum the
matrix SHALL cover `GLB`/`GLTF`, `FBX` and `OBJ`, and SHALL record that `OBJ`
yields no skeleton, no bone count, no animation clips, no frame rate, no
attachment points and no reliable unit scale or up axis. A format not present in
the matrix SHALL be reported as an unsupported export format rather than
validated with assumed facts.

#### Scenario: Matrix governs OBJ
- **WHEN** the fact availability of an `OBJ` export is resolved
- **THEN** animation clips, frame rate, bone count, skinning, attachment points,
  unit scale and up axis SHALL all be marked unavailable
- **AND** triangle count, object names and material names SHALL be marked available

#### Scenario: Unsupported format is refused, not assumed
- **WHEN** validation is requested for an export in a format the matrix does not cover
- **THEN** the system SHALL report an unsupported export format naming the format
- **AND** SHALL NOT report the export as passing

### Requirement: A rule whose facts are unavailable is reported as not evaluated

A rule whose required facts are unavailable for the export's format SHALL be
reported with the outcome **not evaluated**, naming the rule and stating which
fact the format cannot yield. A not-evaluated rule SHALL NOT be counted as
passing and SHALL NOT be counted as a violation, and SHALL NOT by itself change
the overall outcome.

#### Scenario: Unit scale cannot be judged from OBJ
- **GIVEN** an asset declaring `unit_scale: 1.0`
- **WHEN** an `OBJ` export is validated
- **THEN** the unit scale rule SHALL be reported as not evaluated
- **AND** the report SHALL state that the format carries no unit scale

#### Scenario: Not evaluated is distinguishable from passed
- **GIVEN** a validation in which one rule passed and another could not be evaluated
- **WHEN** the report is read
- **THEN** the two rules SHALL be distinguishable by outcome
- **AND** the not-evaluated rule SHALL NOT appear as satisfied

#### Scenario: Not evaluated alone does not fail the run
- **GIVEN** a validation producing no violations and several not-evaluated rules
- **WHEN** the overall outcome is computed
- **THEN** it SHALL be passing

### Requirement: A format that cannot carry a declared requirement is unsuitable

When an asset declares a requirement that the export's format can never contain —
such as animation clips, a skeleton or attachment points for a format that
carries none — the system SHALL report an `error`-severity violation stating that
the format is unsuitable for this asset, naming the declared requirement and the
format. This SHALL be distinguished from a not-evaluated rule: a rule is not
evaluated when the format cannot *record* the fact, and the format is unsuitable
when it cannot *contain* what the specification demands.

#### Scenario: OBJ for an animated asset
- **GIVEN** an asset whose states resolve to required animation clips
- **WHEN** an `OBJ` export is validated for it
- **THEN** an `error`-severity violation SHALL be reported stating that `OBJ` is
  an unsuitable export format for this asset
- **AND** the violation SHALL name the animation clip requirement

#### Scenario: OBJ for a static asset with no such declarations
- **GIVEN** an asset declaring no sockets, no rig and no animated states
- **WHEN** an `OBJ` export is validated for it
- **THEN** no unsuitable-format violation SHALL be reported
- **AND** the rules whose facts `OBJ` cannot yield SHALL be reported as not evaluated

### Requirement: Violation severity and report shape

Every violation SHALL carry a stable machine-readable rule identifier, a
severity of `error` or `warning`, a human-readable message, and the subject it
concerns. A validation report SHALL state the asset, the export examined, the
export's format, the list of violations, the list of rules that could not be
evaluated with the reason for each, and an overall outcome that is failing if and
only if at least one violation has severity `error`.

#### Scenario: Warnings alone pass
- **WHEN** a validation produces only `warning` violations
- **THEN** the overall outcome SHALL be passing
- **AND** the warnings SHALL still be listed in the report

#### Scenario: Stable rule identifiers
- **WHEN** the same rule is violated in two different runs
- **THEN** both violations SHALL carry the same rule identifier

#### Scenario: Not-evaluated rules are listed separately
- **GIVEN** a validation in which two rules could not be evaluated
- **WHEN** the report is produced
- **THEN** it SHALL list those two rules with their reasons
- **AND** they SHALL NOT appear in the list of violations

### Requirement: Machine-readable and human-readable output

A validation report SHALL be renderable both as structured data for automated
consumers and as prose for a person reading it in a terminal or an agent context
window. Both renderings SHALL describe the same violations, and the structured
rendering SHALL be stable enough to be consumed programmatically.

#### Scenario: Both renderings agree
- **WHEN** a report is rendered as structured data and as prose
- **THEN** both SHALL contain the same violations, severities and overall outcome
- **AND** both SHALL contain the same not-evaluated rules with their reasons

### Requirement: Missing or unreadable inputs are reported, not crashed on

When the export file is missing, unreadable, or cannot be parsed as a supported
mesh format, the system SHALL report that condition as a validation failure
identifying the file and the reason, and SHALL NOT present it as a passing
validation.

#### Scenario: Unparseable export
- **WHEN** validation is run against a file that is not a readable mesh
- **THEN** the system SHALL report a failure naming the file and the reason
- **AND** the overall outcome SHALL be failing
