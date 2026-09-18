# Generated from openspec/changes/add-asset-spec-and-validator/specs/asset-validation/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-asset-spec-and-validator @capability:asset-validation @spec:openspec/changes/add-asset-spec-and-validator/specs/asset-validation/spec.md
Feature: asset-validation

  Rule: Validation is a pure decision over extracted mesh facts

    Scenario: Same facts produce the same verdict
      Given two exports in different file formats that yield identical mesh facts
      When both are validated against the same specification
      Then the resulting violations SHALL be identical

    Scenario: An unavailable fact is not defaulted
      Given an export in a format that records no bone count
      When facts are extracted from it
      Then the bone count SHALL be marked unavailable
      And it SHALL NOT be reported as zero or as any other substitute value

  Rule: One verdict across every surface

    Scenario: Command line and application agree
      Given an export that fails its triangle budget
      When it is validated from the command line and again from any other surface
      Then both SHALL report the same violations with the same severities

  Rule: Validation requires no identity and no network

    Scenario: Validation succeeds while services are down
      Given the identity provider and all remote services are unreachable
      When an export is validated locally
      Then validation SHALL complete and report its violations normally

    Scenario: Reporting a result is separable and non-blocking
      Given a configured destination for reporting validation results
      When that destination is unreachable
      Then the validation verdict SHALL still be produced and returned
      And the failure to report SHALL NOT change the verdict

  Rule: Budget rules

    Scenario: Over budget
      Given an effective `tri_budget` of 12000
      When an export containing 14310 triangles is validated
      Then a violation SHALL be reported stating observed 14310 and allowed 12000

    Scenario: Within budget
      Given an effective `tri_budget` of 12000
      When an export containing 11840 triangles is validated
      Then no triangle budget violation SHALL be reported

  Rule: Mechanical convention rules

    Scenario: Unapplied transforms
      When an export contains an object whose transforms are not applied
      Then a violation SHALL be reported naming that object

    Scenario: Naming pattern mismatch
      Given an effective naming pattern of `SM_{asset}_LOD{n}`
      When an export contains an object named `mesh_final_v2`
      Then a violation SHALL be reported naming that object and the expected pattern

  Rule: Declared sockets are enforced

    Scenario: Missing socket blocks the export
      Given `design.sockets` declares `SOCKET_muzzle_l` and `SOCKET_jet_r`
      When an export containing only an attachment point named `SOCKET_jet_r` is validated
      Then exactly one violation SHALL be reported, naming `SOCKET_muzzle_l`

    Scenario: Extra attachment points are not violations
      Given `design.sockets` declares `SOCKET_muzzle_l`
      When an export contains `SOCKET_muzzle_l` and an additional `SOCKET_spare`
      Then no socket violation SHALL be reported

  Rule: Declared animation clips are enforced

    Scenario: Missing clip blocks the export
      Given an asset whose states resolve to required clips `A_mech_scout_walk` and `A_mech_scout_fire`
      When an export containing only a clip named `A_mech_scout_walk` is validated
      Then exactly one violation SHALL be reported, naming `A_mech_scout_fire`
      And the violation SHALL name the state that required it

    Scenario: Extra clips are not violations
      Given an asset whose only required clip is `A_mech_scout_walk`
      When an export contains `A_mech_scout_walk` and an additional `A_mech_scout_test`
      Then no animation clip violation SHALL be reported

    Scenario: An asset requiring no clips is unaffected
      Given an asset whose states all declare themselves unanimated
      When an export containing no animation clips is validated
      Then no animation clip violation SHALL be reported

  Rule: Declared clip expectations are enforced

    Scenario: Frame rate mismatch
      Given a state declaring `frame_rate: 30`
      When its clip is exported at 24 frames per second
      Then a violation SHALL be reported naming the clip, the expected 30 and the observed 24

    Scenario: Missing root motion
      Given a state `walk` declaring `root_motion: true`
      When its clip animates no translation of the root
      Then a violation SHALL be reported naming the clip and the expectation

    Scenario: Clip shorter than the declared minimum
      Given a state declaring a minimum duration of 1.0 second
      When its clip is 0.4 seconds long
      Then a violation SHALL be reported stating observed 0.4 and the declared minimum 1.0

  Rule: Rig budget and skinning are enforced

    Scenario: Over the bone budget
      Given an effective `rig.max_bones` of 96
      When an export whose skeleton has 118 bones is validated
      Then a violation SHALL be reported stating observed 118 and allowed 96

    Scenario: Within the bone budget
      Given an effective `rig.max_bones` of 96
      When an export whose skeleton has 74 bones is validated
      Then no bone budget violation SHALL be reported

    Scenario: Rig declared but export is not skinned
      Given an asset declaring a rig
      When an export containing no skinning is validated
      Then a violation SHALL be reported naming the asset and the declared skeleton

  Rule: Per-format fact availability matrix

    Scenario: Matrix governs OBJ
      When the fact availability of an `OBJ` export is resolved
      Then animation clips, frame rate, bone count, skinning, attachment points, unit scale and up axis SHALL all be marked unavailable
      And triangle count, object names and material names SHALL be marked available

    Scenario: Unsupported format is refused, not assumed
      When validation is requested for an export in a format the matrix does not cover
      Then the system SHALL report an unsupported export format naming the format
      And SHALL NOT report the export as passing

  Rule: A rule whose facts are unavailable is reported as not evaluated

    Scenario: Unit scale cannot be judged from OBJ
      Given an asset declaring `unit_scale: 1.0`
      When an `OBJ` export is validated
      Then the unit scale rule SHALL be reported as not evaluated
      And the report SHALL state that the format carries no unit scale

    Scenario: Not evaluated is distinguishable from passed
      Given a validation in which one rule passed and another could not be evaluated
      When the report is read
      Then the two rules SHALL be distinguishable by outcome
      And the not-evaluated rule SHALL NOT appear as satisfied

    Scenario: Not evaluated alone does not fail the run
      Given a validation producing no violations and several not-evaluated rules
      When the overall outcome is computed
      Then it SHALL be passing

  Rule: A format that cannot carry a declared requirement is unsuitable

    Scenario: OBJ for an animated asset
      Given an asset whose states resolve to required animation clips
      When an `OBJ` export is validated for it
      Then an `error`-severity violation SHALL be reported stating that `OBJ` is an unsuitable export format for this asset
      And the violation SHALL name the animation clip requirement

    Scenario: OBJ for a static asset with no such declarations
      Given an asset declaring no sockets, no rig and no animated states
      When an `OBJ` export is validated for it
      Then no unsuitable-format violation SHALL be reported
      And the rules whose facts `OBJ` cannot yield SHALL be reported as not evaluated

  Rule: Violation severity and report shape

    Scenario: Warnings alone pass
      When a validation produces only `warning` violations
      Then the overall outcome SHALL be passing
      And the warnings SHALL still be listed in the report

    Scenario: Stable rule identifiers
      When the same rule is violated in two different runs
      Then both violations SHALL carry the same rule identifier

    Scenario: Not-evaluated rules are listed separately
      Given a validation in which two rules could not be evaluated
      When the report is produced
      Then it SHALL list those two rules with their reasons
      And they SHALL NOT appear in the list of violations

  Rule: Machine-readable and human-readable output

    Scenario: Both renderings agree
      When a report is rendered as structured data and as prose
      Then both SHALL contain the same violations, severities and overall outcome
      And both SHALL contain the same not-evaluated rules with their reasons

  Rule: Missing or unreadable inputs are reported, not crashed on

    Scenario: Unparseable export
      When validation is run against a file that is not a readable mesh
      Then the system SHALL report a failure naming the file and the reason
      And the overall outcome SHALL be failing
