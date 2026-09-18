# Generated from openspec/changes/add-asset-spec-and-validator/specs/asset-preview/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-asset-spec-and-validator @capability:asset-preview @spec:openspec/changes/add-asset-spec-and-validator/specs/asset-preview/spec.md
Feature: asset-preview

  Rule: Preview is a by-product of validation

    Scenario: Preview emitted during validation
      Given an export that was successfully read for validation
      When preview emission is requested for that run
      Then a preview mesh SHALL be produced from the already-loaded data

    Scenario: Unreadable export produces no preview
      Given an export that could not be read
      When validation runs
      Then no preview SHALL be emitted
      And the validation failure SHALL still be reported

  Rule: Preview is decimated and compressed

    Scenario: Preview is smaller than the source
      Given a working export of substantial size
      When a preview is emitted for it
      Then the preview SHALL contain fewer triangles than the source
      And the preview file SHALL be smaller than the source file

  Rule: Preview preserves anchorable part names

    Scenario: Named parts survive decimation
      Given an export containing a part named `SM_MechScout_Shoulder_L`
      When a preview is emitted
      Then the preview SHALL contain a part with the same name

  Rule: Preview preserves animation clips and skinning

    Scenario: Clips survive decimation
      Given an export containing clips `A_mech_scout_walk` and `A_mech_scout_fire`
      When a preview is emitted
      Then the preview SHALL contain clips with the same two names
      And each clip SHALL have the same duration as in the source

    Scenario: Skinning is preserved
      Given a skinned export whose skeleton has 74 bones
      When a preview is emitted
      Then the preview SHALL be skinned to a skeleton with the same bone names

    Scenario: Clips cannot be preserved
      Given an export whose clips cannot be carried into the preview
      When preview emission runs
      Then the preview SHALL be reported as failed rather than emitted without its clips
      And the validation outcome SHALL be unchanged

    Scenario: A source without clips is not a failure
      Given an export containing no animation clips
      When a preview is emitted
      Then the preview SHALL contain no clips
      And no preview failure SHALL be reported

  Rule: Preview emission never changes the verdict

    Scenario: Preview emission fails
      Given a validation that produced no errors
      When preview emission fails
      Then the validation outcome SHALL remain passing
      And the preview failure SHALL be reported as a distinct condition

  Rule: Preview identifies its source

    Scenario: Preview traceable to its export
      When a preview is emitted for an export of `mech_scout`
      Then the recorded preview SHALL identify `mech_scout` and the source export
