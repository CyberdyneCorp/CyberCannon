# Spec Delta

## Purpose

The `canon` command-line surface — the way a person or an automated hook
validates an export, compiles a specification and checks a spec file, designed to
run inside a pre-commit hook with no configuration ceremony and no credentials.

## ADDED Requirements

### Requirement: Command surface

The command-line tool SHALL provide, at minimum, a command to validate an export
against its asset's specification, a command to compile an asset's specification
into its readable form, and a command to check that specification files are
themselves structurally valid.

#### Scenario: Validate an export
- **WHEN** the user runs the validate command against an export file
- **THEN** the tool SHALL report the violations for that export

#### Scenario: Check specification files
- **WHEN** the user runs the check command over a repository
- **THEN** the tool SHALL report structural violations of every specification file found

### Requirement: Exit codes are stable and scriptable

The tool SHALL exit with code `0` when the requested operation completed and
produced no error-severity violations, `1` when it completed and produced at
least one error-severity violation, and a distinct non-zero code when the
operation could not be performed at all, such as a missing file or an unusable
configuration. These codes SHALL remain stable across releases.

#### Scenario: Clean run
- **WHEN** validation produces no error-severity violations
- **THEN** the tool SHALL exit with code 0

#### Scenario: Violations found
- **WHEN** validation produces at least one error-severity violation
- **THEN** the tool SHALL exit with code 1

#### Scenario: Operation could not run
- **WHEN** the requested export file does not exist
- **THEN** the tool SHALL exit with a non-zero code distinct from 1
- **AND** the message SHALL name the missing file

### Requirement: Human and machine output modes

The tool SHALL print human-readable output by default, and SHALL offer a mode
that emits structured machine-readable output on standard output suitable for
consumption by another program. In the machine-readable mode, no human-oriented
decoration SHALL be written to standard output.

#### Scenario: Machine mode output is parseable
- **WHEN** the tool is run in machine-readable mode
- **THEN** standard output SHALL contain only the structured result
- **AND** any progress or diagnostic text SHALL be written elsewhere

### Requirement: Asset discovery from a path

Given the path of an export or of any file inside an asset's directory, the tool
SHALL locate the governing `asset.yaml` by searching upward from that path within
the repository, so the user does not have to name the specification explicitly.
The user MAY override the discovered specification explicitly.

#### Scenario: Spec found from an export path
- **GIVEN** `characters/mech_scout/asset.yaml` exists
- **WHEN** the tool validates `characters/mech_scout/exports/SM_MechScout_LOD0.glb`
- **THEN** it SHALL use that specification without the user naming it

#### Scenario: No governing spec found
- **WHEN** the tool is run against an export with no `asset.yaml` above it
- **THEN** it SHALL report that no specification was found for the path
- **AND** SHALL exit with the code reserved for an operation that could not run

### Requirement: Runs with no credentials and no configuration ceremony

The tool SHALL run its validation, check and compile commands with no login, no
stored token and no interactive setup step. It SHALL NOT prompt for credentials
and SHALL NOT fail because no identity is configured.

#### Scenario: First run on a fresh machine
- **GIVEN** a machine where the tool has never been run and no identity is configured
- **WHEN** the user validates an export
- **THEN** the tool SHALL complete the validation
- **AND** SHALL NOT prompt for or require credentials

### Requirement: Usable as a pre-commit hook

The tool SHALL support being invoked with a list of changed files and SHALL
validate only the assets those files belong to, so it can serve as a pre-commit
hook without scanning the whole repository. Given no relevant files, it SHALL
exit successfully without work.

#### Scenario: Only touched assets are validated
- **GIVEN** a repository containing many assets
- **WHEN** the tool is invoked with files belonging to one asset
- **THEN** it SHALL validate only that asset

#### Scenario: Nothing relevant changed
- **WHEN** the tool is invoked with files that belong to no asset
- **THEN** it SHALL exit with code 0 without reporting violations

### Requirement: Violation messages state the fix

Every violation printed by the tool SHALL identify the asset, the subject at
fault, the observed value and the expected value, so that the reader can act
without opening the specification.

#### Scenario: Actionable message
- **WHEN** a triangle budget violation is printed
- **THEN** the message SHALL name the asset, the observed triangle count and the
  allowed triangle count
