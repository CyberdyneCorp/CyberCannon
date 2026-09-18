# Spec Delta

## Purpose

Produces a small, compressed preview mesh as a by-product of a validation run
that has already loaded the export, so later surfaces can display and animate an
asset without ever transferring the full working export.

## ADDED Requirements

### Requirement: Preview is a by-product of validation

When an export is validated and the mesh was successfully read, the system SHALL
be able to emit a preview mesh derived from that same read, without reading or
loading the export a second time.

#### Scenario: Preview emitted during validation
- **GIVEN** an export that was successfully read for validation
- **WHEN** preview emission is requested for that run
- **THEN** a preview mesh SHALL be produced from the already-loaded data

#### Scenario: Unreadable export produces no preview
- **GIVEN** an export that could not be read
- **WHEN** validation runs
- **THEN** no preview SHALL be emitted
- **AND** the validation failure SHALL still be reported

### Requirement: Preview is decimated and compressed

A preview mesh SHALL be reduced in triangle count relative to the source export
and SHALL be stored in a compressed form suitable for direct delivery to a web
browser. The system SHALL NOT designate the working export as the preview.

#### Scenario: Preview is smaller than the source
- **GIVEN** a working export of substantial size
- **WHEN** a preview is emitted for it
- **THEN** the preview SHALL contain fewer triangles than the source
- **AND** the preview file SHALL be smaller than the source file

### Requirement: Preview preserves anchorable part names

A preview mesh SHALL preserve the object and attachment point names present in
the source export, so that annotations anchored to a named part resolve
identically against the preview and against the source.

#### Scenario: Named parts survive decimation
- **GIVEN** an export containing a part named `SM_MechScout_Shoulder_L`
- **WHEN** a preview is emitted
- **THEN** the preview SHALL contain a part with the same name

### Requirement: Preview preserves animation clips and skinning

A preview mesh SHALL preserve every animation clip present in the source export
with the same clip names and the same durations, and SHALL preserve the skeleton
and the skinning that binds the mesh to it, so that a clip plays on the preview
exactly as it plays on the source. Decimation SHALL NOT be allowed to drop
skinning, bones or clips in order to reach its triangle target. A source export
containing no clips SHALL yield a preview containing no clips, and that SHALL NOT
be reported as a preview failure.

#### Scenario: Clips survive decimation
- **GIVEN** an export containing clips `A_mech_scout_walk` and `A_mech_scout_fire`
- **WHEN** a preview is emitted
- **THEN** the preview SHALL contain clips with the same two names
- **AND** each clip SHALL have the same duration as in the source

#### Scenario: Skinning is preserved
- **GIVEN** a skinned export whose skeleton has 74 bones
- **WHEN** a preview is emitted
- **THEN** the preview SHALL be skinned to a skeleton with the same bone names

#### Scenario: Clips cannot be preserved
- **GIVEN** an export whose clips cannot be carried into the preview
- **WHEN** preview emission runs
- **THEN** the preview SHALL be reported as failed rather than emitted without
  its clips
- **AND** the validation outcome SHALL be unchanged

#### Scenario: A source without clips is not a failure
- **GIVEN** an export containing no animation clips
- **WHEN** a preview is emitted
- **THEN** the preview SHALL contain no clips
- **AND** no preview failure SHALL be reported

### Requirement: Preview emission never changes the verdict

Failure to emit a preview SHALL NOT alter the validation outcome, and SHALL be
reported separately from validation violations.

#### Scenario: Preview emission fails
- **GIVEN** a validation that produced no errors
- **WHEN** preview emission fails
- **THEN** the validation outcome SHALL remain passing
- **AND** the preview failure SHALL be reported as a distinct condition

### Requirement: Preview identifies its source

An emitted preview SHALL be associated with the asset identifier and the export
it was derived from, so a consumer can tell which export a preview represents and
whether it is current.

#### Scenario: Preview traceable to its export
- **WHEN** a preview is emitted for an export of `mech_scout`
- **THEN** the recorded preview SHALL identify `mech_scout` and the source export
