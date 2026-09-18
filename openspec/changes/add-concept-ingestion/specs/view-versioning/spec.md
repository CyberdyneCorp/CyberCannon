# Spec Delta

## Purpose

The revision history of a concept view. Because a view is a file in the
repository, replacing it is a commit and its predecessor is still there — so this
capability is about reading that history honestly: listing revisions, retrieving
one, comparing two, never destroying an earlier one, and stating out loud what
became of the annotations anchored to a view that was replaced.

## ADDED Requirements

### Requirement: Replacing a view creates a revision and destroys nothing

Replacing the image in a view slot SHALL write to the same repository path,
producing a new revision of that view while the superseded image remains
retrievable from the repository's history. Removing a view SHALL likewise be
recorded as a revision, after which earlier revisions SHALL still be retrievable.
No ingestion, replacement or removal SHALL make an earlier revision unreachable.

#### Scenario: Three uploads, three revisions
- **GIVEN** a `front` view that has been uploaded and then replaced twice
- **WHEN** its revisions are listed
- **THEN** three revisions SHALL be listed and each SHALL be retrievable

#### Scenario: Removing a view keeps its history
- **GIVEN** a view with two revisions
- **WHEN** the view is removed
- **THEN** both earlier revisions SHALL still be retrievable
- **AND** the view SHALL be reported as removed rather than as never having existed

#### Scenario: An identical re-upload is not a revision
- **GIVEN** a view whose current revision has a given content hash
- **WHEN** a byte-identical image is uploaded to the same slot
- **THEN** no new revision SHALL be created
- **AND** the result SHALL report the view as unchanged

### Requirement: Listing a view's revisions

The system SHALL list the revisions of a view newest first. Each entry SHALL carry
a stable revision identifier, the person credited with it, the time it was
recorded, and the content hash of the image at that revision. Exactly one entry
SHALL be marked as the current revision, unless the view has been removed, in
which case none SHALL be.

#### Scenario: A revision list is complete and ordered
- **GIVEN** a view with three revisions
- **WHEN** its revisions are listed
- **THEN** three entries SHALL be returned newest first
- **AND** each SHALL carry an identifier, a person, a time and a content hash
- **AND** exactly one SHALL be marked current

#### Scenario: Revision identifiers are stable
- **WHEN** the same view's revisions are listed twice with no intervening change
- **THEN** both listings SHALL report the same identifiers for the same revisions

#### Scenario: A removed view has no current revision
- **GIVEN** a view that has been removed
- **WHEN** its revisions are listed
- **THEN** the earlier revisions SHALL be listed and none SHALL be marked current

### Requirement: Retrieving a specific revision

The system SHALL return the image of any listed revision when given its
identifier. A revision that is not the current one SHALL be labelled as historical
together with its identifier, and SHALL NOT be presented as the view's current
image. An identifier that names no revision of that view SHALL produce an explicit
not-found result naming the identifier, never the current revision as a fallback.

#### Scenario: A historical revision is labelled
- **WHEN** a superseded revision is retrieved by its identifier
- **THEN** its image SHALL be returned
- **AND** it SHALL be labelled historical with its revision identifier

#### Scenario: Unknown revision identifier
- **WHEN** a revision identifier that does not belong to the view is requested
- **THEN** an explicit not-found result naming the identifier SHALL be returned
- **AND** the current revision SHALL NOT be returned in its place

### Requirement: Comparing two revisions

The system SHALL compare any two revisions of the same view, presenting both
images together with, for each: its revision identifier, the person credited, the
time, the pixel dimensions, the byte size and the content hash. The comparison
SHALL be available whether or not either revision is the current one, and SHALL
present the older revision first regardless of the order the two were requested
in. Comparing a revision with itself SHALL report the two as identical rather than
fail.

#### Scenario: Comparing a superseded revision with the current one
- **GIVEN** a view with revisions `r1` and `r2` where `r2` is current
- **WHEN** the two are compared
- **THEN** both images SHALL be presented with their identifier, person, time, dimensions, byte size and content hash

#### Scenario: Argument order does not change the presentation
- **GIVEN** revisions `r1` and `r2` of one view
- **WHEN** they are compared as `r2, r1` and again as `r1, r2`
- **THEN** both comparisons SHALL present `r1` as the older revision

#### Scenario: Comparing two historical revisions
- **GIVEN** a view with three revisions of which the third is current
- **WHEN** the first and second are compared
- **THEN** the comparison SHALL be produced normally

#### Scenario: Comparing a revision with itself
- **WHEN** a revision is compared with itself
- **THEN** the result SHALL report the two as identical

### Requirement: Revision history is served from the repository alone

Listing, retrieving and comparing revisions SHALL depend only on the repository
and SHALL succeed with every mirrored blob and every thumbnail deleted. No
revision SHALL be retrievable only from the mirror.

#### Scenario: History survives a wiped mirror
- **GIVEN** a view with three revisions and an emptied blob store
- **WHEN** its revisions are listed and a superseded one is retrieved
- **THEN** both SHALL succeed using the repository

### Requirement: Incomplete history is reported, never presented as complete

When the repository working copy does not contain the full history of a view, the
system SHALL list the revisions it has and SHALL state that revisions before a
named point are unavailable. It SHALL NOT present a truncated list as the view's
complete history.

#### Scenario: Shallow working copy
- **GIVEN** a working copy whose history is truncated
- **WHEN** a view's revisions are listed
- **THEN** the available revisions SHALL be listed
- **AND** the result SHALL state that earlier revisions are unavailable and from which point

### Requirement: Annotations on a replaced view are carried or orphaned, never silently moved

Every annotation anchored to a view SHALL record the revision of the view it was
authored against. When that view is replaced, each annotation anchored to it SHALL
be assigned exactly one of two states: **carried**, meaning its anchor remains
valid against the new revision, or **orphaned**, meaning it does not. The
assignment SHALL be mechanical: an annotation SHALL be carried when the new
revision's aspect ratio equals the superseded revision's within the configured
tolerance, and SHALL be orphaned otherwise. The resulting state SHALL be visible on
the annotation together with the revision it was authored against. No annotation
SHALL be presented at a position on a revision it was not authored against without
being marked as carried.

#### Scenario: Same aspect ratio carries the pins
- **GIVEN** a view with four annotations anchored to it
- **WHEN** it is replaced by an image of the same aspect ratio
- **THEN** all four annotations SHALL be marked carried
- **AND** each SHALL still name the revision it was authored against

#### Scenario: A different aspect ratio orphans the pins
- **GIVEN** a view with four annotations anchored to it
- **WHEN** it is replaced by an image of a different aspect ratio
- **THEN** all four annotations SHALL be marked orphaned
- **AND** none SHALL be displayed at a position on the new revision

#### Scenario: The outcome is never silent
- **WHEN** a view carrying annotations is replaced
- **THEN** the result of the replacement SHALL state how many annotations were carried and how many were orphaned

#### Scenario: An orphan can still be read against its own revision
- **GIVEN** an orphaned annotation
- **WHEN** it is opened
- **THEN** the revision it was authored against SHALL be retrievable and its position on that revision SHALL be shown

### Requirement: Orphaning is an anchor state, not an exit

An orphaned annotation SHALL remain open and SHALL still require one of the two
exits: promoted to a durable rule, or resolved as an issue. Orphaning SHALL NOT
delete, resolve or promote an annotation, and an orphaned open annotation SHALL
still appear among the open issues of the asset's compiled briefing.

#### Scenario: Orphans still appear in the compiled briefing
- **GIVEN** an asset with one orphaned open annotation
- **WHEN** its briefing is compiled
- **THEN** that annotation SHALL appear among the open issues

#### Scenario: Replacement resolves nothing
- **GIVEN** a view with three open annotations
- **WHEN** it is replaced such that all three are orphaned
- **THEN** all three SHALL still be open
- **AND** none SHALL be recorded as promoted or resolved

### Requirement: Re-anchoring an orphan is an explicit human action

A person SHALL be able to re-anchor an orphaned annotation to the current revision
of its view. Re-anchoring SHALL record who did it and when, and SHALL leave the
annotation's content and its exit state unchanged. The system SHALL NOT re-anchor
an orphaned annotation automatically, by inference from image content or
otherwise.

#### Scenario: A person re-anchors an orphan
- **GIVEN** an orphaned annotation
- **WHEN** a person re-anchors it to a position on the current revision
- **THEN** it SHALL be marked carried against that revision
- **AND** the person and time of re-anchoring SHALL be recorded
- **AND** its text and its open state SHALL be unchanged

#### Scenario: Nothing re-anchors itself
- **GIVEN** an orphaned annotation and a view that is replaced again
- **WHEN** no person re-anchors it
- **THEN** it SHALL still be orphaned
