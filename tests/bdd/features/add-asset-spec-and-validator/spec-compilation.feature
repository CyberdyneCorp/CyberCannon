# Generated from openspec/changes/add-asset-spec-and-validator/specs/spec-compilation/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-asset-spec-and-validator @capability:spec-compilation @spec:openspec/changes/add-asset-spec-and-validator/specs/spec-compilation/spec.md
Feature: spec-compilation

  Rule: Compiled spec contains rules and open issues only

    Scenario: Resolved annotation is excluded
      Given an asset with one open annotation and three resolved annotations
      When its specification is compiled
      Then the output SHALL contain the open annotation
      And the output SHALL NOT contain any of the resolved annotations

    Scenario: Promoted content appears as a rule, not as history
      Given an annotation that was promoted into the asset's rules
      When the specification is compiled
      Then the promoted content SHALL appear among the rules
      And the original annotation SHALL NOT appear as an open item

    Scenario: Output does not grow with usage
      Given an asset that accumulates and then resolves many annotations over time
      When its specification is compiled after each resolution
      Then the compiled output SHALL NOT grow as a result of resolved annotations

  Rule: Compiled output is self-explanatory

    Scenario: Read cold
      When the compiled output is read with no other context
      Then it SHALL identify the asset, its current status, and which discipline authored each part of the contract

  Rule: Effective values are resolved at compile time

    Scenario: Defaults merged into output
      Given a project default `up_axis: Z` and an asset that declares no up axis
      When the specification is compiled
      Then the output SHALL state an up axis of `Z`

  Rule: Compilation is deterministic and offline

    Scenario: Repeated compilation is identical
      When the same unchanged specification is compiled twice
      Then the two outputs SHALL be byte-identical

    Scenario: Compiles while offline
      Given no network connectivity
      When a specification is compiled
      Then compilation SHALL succeed

  Rule: Compiled output is a derived artifact

    Scenario: Compiled file edited by hand
      Given a hand-edited `art-spec.md`
      When the specification is compiled again
      Then the hand edits SHALL be replaced by the output derived from `asset.yaml`

  Rule: Project-level constraint briefing

    Scenario: Project briefing excludes per-asset content
      When the project-level briefing is compiled
      Then it SHALL contain the project's shared constraints and rules
      And it SHALL NOT contain any individual asset's annotations
