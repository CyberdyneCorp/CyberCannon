# Spec Delta

## Purpose

The bridge from proposal to canon — how a person turns a suggested alias into
authored content in `asset.yaml`, attributed to them, reviewable in a normal
diff, and how the system behaves when the image behind a suggestion later changes.

## ADDED Requirements

### Requirement: Acceptance is a human action

A suggestion SHALL become content of a specification only through an explicit act
of acceptance by an identified person. There SHALL be no automatic, scheduled or
bulk-by-default path from generation to acceptance.

#### Scenario: Nothing is accepted without a person
- **GIVEN** generated suggestions for many assets
- **WHEN** no person acts on them
- **THEN** no specification file SHALL change

#### Scenario: Acceptance requires an identified actor
- **WHEN** acceptance is attempted with no resolvable person
- **THEN** it SHALL be refused

### Requirement: Accepted content becomes ordinary authored content

On acceptance, the accepted value SHALL be written into the asset's specification
in the same form as any human-authored value, and SHALL be indistinguishable in
the file from a value typed by hand. The specification SHALL NOT record that the
value originated from a model.

#### Scenario: Accepted alias is a normal alias
- **WHEN** a suggested alias is accepted
- **THEN** it SHALL appear in the specification's aliases exactly as a
  hand-written alias would
- **AND** the file SHALL contain no marker distinguishing it

#### Scenario: Accepted alias ranks as an alias
- **WHEN** a previously suggested alias has been accepted
- **THEN** search SHALL rank it as an accepted alias

### Requirement: Acceptance is attributed to the accepting person

The system SHALL record which person accepted each suggestion and when, so that
responsibility for the content rests with a person. The record of acceptance SHALL
be retrievable even though the specification file itself carries no marker.

#### Scenario: Accepting person recorded
- **WHEN** a person accepts a suggestion
- **THEN** the acceptance record SHALL identify that person and the time

### Requirement: Partial acceptance

A person SHALL be able to accept a subset of the suggested values, edit a value
before accepting it, and reject the remainder. Accepting one suggestion SHALL NOT
accept any other.

#### Scenario: Subset accepted
- **GIVEN** four suggested aliases
- **WHEN** a person accepts two of them
- **THEN** exactly those two SHALL be written to the specification

#### Scenario: Edited before acceptance
- **WHEN** a person edits a suggested value and accepts the edited form
- **THEN** the edited value SHALL be written
- **AND** the acceptance SHALL be attributed to that person

### Requirement: Rejection is recorded and suppresses re-suggestion

A rejected suggestion SHALL be recorded as rejected for its source content, and
SHALL NOT be presented again for the same unchanged source.

#### Scenario: Rejected suggestion does not return
- **GIVEN** a suggestion rejected for an image
- **WHEN** suggestions for that unchanged image are presented again
- **THEN** the rejected value SHALL NOT appear

### Requirement: Writes preserve the file a human wrote

Writing an accepted value into a specification SHALL preserve the file's existing
comments, key order and formatting, changing only what acceptance requires, so
that the resulting change is reviewable as a normal difference.

#### Scenario: Only the intended change appears
- **GIVEN** a specification containing comments and a specific key order
- **WHEN** an accepted alias is written into it
- **THEN** the difference SHALL show only the added alias
- **AND** comments and key order SHALL be unchanged

### Requirement: Acceptance survives regeneration of its source

Once accepted, a value SHALL remain in the specification regardless of later
regeneration, image replacement, or deletion of derived records. Changing the
image SHALL NOT remove or alter previously accepted content.

#### Scenario: Image replaced after acceptance
- **GIVEN** an accepted alias derived from an image
- **WHEN** that image is replaced and metadata is regenerated
- **THEN** the accepted alias SHALL remain in the specification unchanged

### Requirement: A failed write leaves the specification untouched

If writing an accepted value cannot complete, the specification file SHALL be left
exactly as it was, and the suggestion SHALL remain unaccepted so the action can be
retried.

#### Scenario: Interrupted write
- **WHEN** writing an accepted value fails partway
- **THEN** the specification file SHALL be unchanged
- **AND** the suggestion SHALL still be pending
