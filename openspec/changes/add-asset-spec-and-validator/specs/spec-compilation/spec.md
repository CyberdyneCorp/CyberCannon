# Spec Delta

## Purpose

Compiles an asset's `asset.yaml` into `art-spec.md`, a clean briefing that a
person or an agent reads to understand what the asset must be — carrying durable
rules and currently open issues, and deliberately excluding the dead thread
archive so the context does not degrade as the tool is used.

## ADDED Requirements

### Requirement: Compiled spec contains rules and open issues only

The compiled `art-spec.md` for an asset SHALL contain its durable content — the
concept description and silhouette rules, the design declarations, and the
engineering constraints — plus its currently open annotations. It SHALL NOT
contain annotations that have been resolved or promoted.

#### Scenario: Resolved annotation is excluded
- **GIVEN** an asset with one open annotation and three resolved annotations
- **WHEN** its specification is compiled
- **THEN** the output SHALL contain the open annotation
- **AND** the output SHALL NOT contain any of the resolved annotations

#### Scenario: Promoted content appears as a rule, not as history
- **GIVEN** an annotation that was promoted into the asset's rules
- **WHEN** the specification is compiled
- **THEN** the promoted content SHALL appear among the rules
- **AND** the original annotation SHALL NOT appear as an open item

#### Scenario: Output does not grow with usage
- **GIVEN** an asset that accumulates and then resolves many annotations over time
- **WHEN** its specification is compiled after each resolution
- **THEN** the compiled output SHALL NOT grow as a result of resolved annotations

### Requirement: Compiled output is self-explanatory

The compiled output SHALL be readable by someone who has never used this tool —
a new team member, an external contractor, or a language model reading the
repository — without requiring any other document to interpret it. It SHALL name
the asset, state its status, and attribute each block to its authoring
discipline.

#### Scenario: Read cold
- **WHEN** the compiled output is read with no other context
- **THEN** it SHALL identify the asset, its current status, and which discipline
  authored each part of the contract

### Requirement: Effective values are resolved at compile time

The compiled output SHALL present the **effective** constraints for the asset,
with project-level defaults already merged and asset-level declarations taking
precedence, so that a reader never has to consult the project configuration to
know what applies.

#### Scenario: Defaults merged into output
- **GIVEN** a project default `up_axis: Z` and an asset that declares no up axis
- **WHEN** the specification is compiled
- **THEN** the output SHALL state an up axis of `Z`

### Requirement: Compilation is deterministic and offline

Compiling the same specification twice SHALL produce byte-identical output.
Compilation SHALL require only the specification file and the project
configuration, with no identity, no network access and no derived store.

#### Scenario: Repeated compilation is identical
- **WHEN** the same unchanged specification is compiled twice
- **THEN** the two outputs SHALL be byte-identical

#### Scenario: Compiles while offline
- **GIVEN** no network connectivity
- **WHEN** a specification is compiled
- **THEN** compilation SHALL succeed

### Requirement: Compiled output is a derived artifact

`art-spec.md` SHALL be reproducible at any time from `asset.yaml`. The system
SHALL NOT treat the compiled file as an input, and editing it SHALL NOT change an
asset's specification.

#### Scenario: Compiled file edited by hand
- **GIVEN** a hand-edited `art-spec.md`
- **WHEN** the specification is compiled again
- **THEN** the hand edits SHALL be replaced by the output derived from `asset.yaml`

### Requirement: Project-level constraint briefing

The system SHALL be able to compile a project-wide briefing containing the
project's shared constraints and golden rules without any single asset's
concept or annotations, so that an agent or person can be given the project's
standing rules alone.

#### Scenario: Project briefing excludes per-asset content
- **WHEN** the project-level briefing is compiled
- **THEN** it SHALL contain the project's shared constraints and rules
- **AND** it SHALL NOT contain any individual asset's annotations
