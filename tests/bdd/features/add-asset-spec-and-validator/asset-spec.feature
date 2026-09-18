# Generated from openspec/changes/add-asset-spec-and-validator/specs/asset-spec/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-asset-spec-and-validator @capability:asset-spec @spec:openspec/changes/add-asset-spec-and-validator/specs/asset-spec/spec.md
Feature: asset-spec

  Rule: Spec file location and source of truth

    Scenario: Spec read directly from a working copy
      Given a game repository containing `characters/mech_scout/asset.yaml`
      When the system is asked for the specification of `mech_scout`
      Then it SHALL read the file from the working copy
      And it SHALL NOT require any database, service or network connection

    Scenario: Derived index is disposable
      Given any derived index of specifications exists
      When that index is deleted
      Then re-scanning the repository SHALL restore it completely
      And no specification data SHALL be lost

  Rule: Asset identity and aliases

    Scenario: Duplicate id within a project
      Given two specification files in the same project declare `id: mech_scout`
      When the project is validated
      Then the system SHALL report a violation naming both file paths

    Scenario: Renaming does not break references
      Given an asset with `id: mech_scout` and `name: "Scout Mech"`
      When `name` is changed to `"Recon Walker"`
      Then the `id` SHALL remain `mech_scout`
      And existing references to `mech_scout` SHALL continue to resolve

  Rule: Three authored blocks with distinct authorship

    Scenario: Concept-only asset is valid
      Given a specification declaring identity and a `concept` block only
      When the specification file is validated
      Then it SHALL be reported as a valid specification
      And the absence of `design` and `constraints` SHALL NOT be a violation

  Rule: Design fields must constrain or be checkable

    Scenario: Declared socket becomes an export gate
      Given a specification whose `design.sockets` declares `SOCKET_muzzle_l`
      When an export for that asset is validated
      Then the absence of an attachment point named `SOCKET_muzzle_l` SHALL be reported as a violation

  Rule: Design states declare an animation contract

    Scenario: A named state becomes an export gate
      Given a specification whose `design.states` lists `fire`
      And a clip naming convention resolving that state to `A_mech_scout_fire`
      When an export for that asset is validated
      Then the absence of an animation clip named `A_mech_scout_fire` SHALL be reported as a violation

    Scenario: A state with no animation is declared explicitly
      Given a state `destroyed` declaring that it has no animation
      When the specification file is validated
      Then it SHALL be reported as valid
      And no animation clip SHALL be required for that state

    Scenario: A state that constrains nothing is rejected
      Given a state that names no clip, resolves to no clip through any convention, and does not declare itself unanimated
      When the specification file is validated
      Then a violation SHALL be reported naming that state

  Rule: Animation clip names follow a declared convention

    Scenario: Template expands to the required clip name
      Given a clip naming convention of `A_{asset}_{state}`
      And an asset `mech_scout` with a state `walk`
      When the required clips are resolved
      Then the required clip name SHALL be `A_mech_scout_walk`

    Scenario: An explicit clip name wins over the convention
      Given a clip naming convention of `A_{asset}_{state}`
      And a state `walk` declaring `clip: Locomotion_Walk_Fwd`
      When the required clips are resolved
      Then the required clip name SHALL be `Locomotion_Walk_Fwd`
      And `A_mech_scout_walk` SHALL NOT be required

  Rule: Engineering constraints block

    Scenario: Asset constraint overrides project default
      Given a project default of `tri_budget: 8000`
      And an asset declaring `tri_budget: 12000`
      When an export for that asset is validated
      Then the effective budget SHALL be 12000

    Scenario: Project default applies when asset is silent
      Given a project default of `up_axis: Z`
      And an asset declaring no `up_axis`
      When an export for that asset is validated
      Then the effective up axis SHALL be `Z`

    Scenario: Bone budget inherited from the project
      Given a project default of `rig.max_bones: 96`
      And an asset declaring a `rig` without `max_bones`
      When an export for that asset is validated
      Then the effective bone budget SHALL be 96

  Rule: Status lifecycle

    Scenario: Unknown status rejected
      When a specification declares `status: wip`
      Then the system SHALL report a violation naming the allowed values

  Rule: Tri-disciplinary ownership

    Scenario: Owners are independent
      Given a specification declaring `owner_art` and `owner_code` but no `owner_design`
      When the specification file is validated
      Then it SHALL be reported as valid
      And the missing `owner_design` SHALL be reported at most as a warning

  Rule: Links to related artifacts

    Scenario: Unreachable link does not invalidate the spec
      Given a specification whose `links.discussion` points to an unreachable URL
      When the specification file is validated
      Then it SHALL be reported as valid
      And no network request SHALL be made

  Rule: Annotation entries with durable dual anchors

    Scenario: Anchor survives a remesh
      Given an annotation anchored to part `SM_MechScout_Shoulder_L`
      When the mesh is retopologised and re-exported with that part still present
      Then the annotation SHALL still resolve to that part
      And its recorded point and normal SHALL be treated as hints, not identity

    Scenario: Missing part yields an orphan, not a wrong placement
      Given an annotation anchored to part `SM_MechScout_Shoulder_L`
      When that part is renamed or removed from the export
      Then the annotation SHALL be reported as orphaned
      And the system SHALL NOT silently relocate it to another part

  Rule: Annotations have exactly two exits

    Scenario: Promotion retires the annotation
      Given an open annotation stating that lens glow is always emissive
      When it is promoted to a rule
      Then the rule SHALL appear in the asset's durable rules
      And the annotation SHALL be marked promoted and SHALL NOT remain open

    Scenario: Resolution does not become permanent context
      Given an annotation reporting that an arm clips at 45 degrees
      When it is resolved
      Then it SHALL be marked resolved
      And it SHALL NOT be presented as a standing rule of the asset

  Rule: Specification file validity is checkable offline

    Scenario: Ascending LOD list rejected
      When a specification declares `lods: [2000, 6000, 12000]`
      Then the system SHALL report a violation stating LOD triangle counts must be descending

    Scenario: Unknown field reported
      When a specification declares a field not defined by the schema
      Then the system SHALL report it, naming the field and its location in the file
