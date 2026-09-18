# Generated from openspec/changes/add-asset-spec-and-validator/specs/canon-cli/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-asset-spec-and-validator @capability:canon-cli @spec:openspec/changes/add-asset-spec-and-validator/specs/canon-cli/spec.md
Feature: canon-cli

  Rule: Command surface

    Scenario: Validate an export
      When the user runs the validate command against an export file
      Then the tool SHALL report the violations for that export

    Scenario: Check specification files
      When the user runs the check command over a repository
      Then the tool SHALL report structural violations of every specification file found

  Rule: Exit codes are stable and scriptable

    Scenario: Clean run
      When validation produces no error-severity violations
      Then the tool SHALL exit with code 0

    Scenario: Violations found
      When validation produces at least one error-severity violation
      Then the tool SHALL exit with code 1

    Scenario: Operation could not run
      When the requested export file does not exist
      Then the tool SHALL exit with a non-zero code distinct from 1
      And the message SHALL name the missing file

  Rule: Human and machine output modes

    Scenario: Machine mode output is parseable
      When the tool is run in machine-readable mode
      Then standard output SHALL contain only the structured result
      And any progress or diagnostic text SHALL be written elsewhere

  Rule: Asset discovery from a path

    Scenario: Spec found from an export path
      Given `characters/mech_scout/asset.yaml` exists
      When the tool validates `characters/mech_scout/exports/SM_MechScout_LOD0.glb`
      Then it SHALL use that specification without the user naming it

    Scenario: No governing spec found
      When the tool is run against an export with no `asset.yaml` above it
      Then it SHALL report that no specification was found for the path
      And SHALL exit with the code reserved for an operation that could not run

  Rule: Runs with no credentials and no configuration ceremony

    Scenario: First run on a fresh machine
      Given a machine where the tool has never been run and no identity is configured
      When the user validates an export
      Then the tool SHALL complete the validation
      And SHALL NOT prompt for or require credentials

  Rule: Usable as a pre-commit hook

    Scenario: Only touched assets are validated
      Given a repository containing many assets
      When the tool is invoked with files belonging to one asset
      Then it SHALL validate only that asset

    Scenario: Nothing relevant changed
      When the tool is invoked with files that belong to no asset
      Then it SHALL exit with code 0 without reporting violations

  Rule: Violation messages state the fix

    Scenario: Actionable message
      When a triangle budget violation is printed
      Then the message SHALL name the asset, the observed triangle count and the allowed triangle count
