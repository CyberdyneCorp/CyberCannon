# Generated from openspec/changes/add-derived-metadata/specs/metadata-acceptance/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-derived-metadata @capability:metadata-acceptance @spec:openspec/changes/add-derived-metadata/specs/metadata-acceptance/spec.md
Feature: metadata-acceptance

  Rule: Acceptance is a human action

    Scenario: Nothing is accepted without a person
      Given generated suggestions for many assets
      When no person acts on them
      Then no specification file SHALL change

    Scenario: Acceptance requires an identified actor
      When acceptance is attempted with no resolvable person
      Then it SHALL be refused

  Rule: Accepted content becomes ordinary authored content

    Scenario: Accepted alias is a normal alias
      When a suggested alias is accepted
      Then it SHALL appear in the specification's aliases exactly as a hand-written alias would
      And the file SHALL contain no marker distinguishing it

    Scenario: Accepted alias ranks as an alias
      When a previously suggested alias has been accepted
      Then search SHALL rank it as an accepted alias

  Rule: Acceptance is attributed to the accepting person

    Scenario: Accepting person recorded
      When a person accepts a suggestion
      Then the acceptance record SHALL identify that person and the time

  Rule: Partial acceptance

    Scenario: Subset accepted
      Given four suggested aliases
      When a person accepts two of them
      Then exactly those two SHALL be written to the specification

    Scenario: Edited before acceptance
      When a person edits a suggested value and accepts the edited form
      Then the edited value SHALL be written
      And the acceptance SHALL be attributed to that person

  Rule: Rejection is recorded and suppresses re-suggestion

    Scenario: Rejected suggestion does not return
      Given a suggestion rejected for an image
      When suggestions for that unchanged image are presented again
      Then the rejected value SHALL NOT appear

  Rule: Writes preserve the file a human wrote

    Scenario: Only the intended change appears
      Given a specification containing comments and a specific key order
      When an accepted alias is written into it
      Then the difference SHALL show only the added alias
      And comments and key order SHALL be unchanged

  Rule: Acceptance survives regeneration of its source

    Scenario: Image replaced after acceptance
      Given an accepted alias derived from an image
      When that image is replaced and metadata is regenerated
      Then the accepted alias SHALL remain in the specification unchanged

  Rule: A failed write leaves the specification untouched

    Scenario: Interrupted write
      When writing an accepted value fails partway
      Then the specification file SHALL be unchanged
      And the suggestion SHALL still be pending
