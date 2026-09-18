# Spec Delta

## Purpose

Links long-form design documents to an asset or a project without rebuilding an
editor: what a link stores, how it is displayed, opened, listed and created, how
it behaves when the document is gone or forbidden, and the boundary that keeps
checkable facts in the specification and rationale in the document.

## ADDED Requirements

### Requirement: A linked document is a reference, never a mirror

A link to a long-form document SHALL be stored as a reference identifying the
document — its workspace, its identifier and an address at which it can be opened
— together with the person who created the link and when. The system SHALL NOT
store, copy or version the document's body, and SHALL NOT present any locally
held copy as the current document. Anything resolved about a document for display
SHALL be held only in rebuildable storage and SHALL be reconstructible by asking
the document platform again.

#### Scenario: Only the reference is authored
- **GIVEN** a document containing several pages of prose
- **WHEN** it is linked to an asset
- **THEN** the asset's specification file SHALL contain only the reference and its
  authorship
- **AND** it SHALL NOT contain any of the document's body text

#### Scenario: Resolved display data is disposable
- **GIVEN** an asset with linked documents whose titles have been resolved
- **WHEN** all rebuildable storage is deleted and rebuilt
- **THEN** the same links SHALL be listed with the same references
- **AND** their titles SHALL be resolved again from the document platform

#### Scenario: Editing happens elsewhere
- **WHEN** a person acts on a linked document from within the system
- **THEN** the only available actions SHALL be opening it at the document platform
  and removing the link
- **AND** no interface for editing the document's contents SHALL be offered

### Requirement: Documents link to an asset or to a project

A document reference SHALL be attachable to a single asset or to the project as a
whole. An asset-scoped link SHALL be stored as authored content in that asset's
specification file, and a project-scoped link in the project's configuration, so
that both are versioned by the repository alongside everything else authored
there. Creating or removing a link SHALL be attributed to the acting person.

#### Scenario: Asset link is versioned with the asset
- **WHEN** a person links a document to an asset
- **THEN** the change SHALL appear as a modification to that asset's specification
  file attributed to that person

#### Scenario: Project link is visible from every asset
- **GIVEN** a document linked at project scope
- **WHEN** any asset in that project is viewed
- **THEN** that document SHALL be listed as a project-scoped link, distinguished
  from the asset's own links

#### Scenario: Removing a link leaves the document untouched
- **WHEN** a person removes a document link
- **THEN** the reference SHALL be removed from the specification
- **AND** the document at the document platform SHALL NOT be modified or deleted

### Requirement: A link resolves to a readable title and short summary

For display, the system SHALL resolve a stored reference to the document's current
title and a short summary of at most a few lines, obtained from the document
platform. Resolution SHALL be performed with the viewing person's own authority,
and a resolved title or summary SHALL NOT be shown to a person who has not been
granted access to that document. When a title cannot be resolved, the reference
SHALL still be displayed using its address.

#### Scenario: Link list reads as documents
- **GIVEN** an asset with two linked documents the viewer may read
- **WHEN** the viewer lists the asset's links
- **THEN** each SHALL be shown with its current title and summary

#### Scenario: Title follows a rename at the source
- **GIVEN** a linked document whose title was resolved previously
- **WHEN** the document is renamed at the document platform and the link is viewed
  again
- **THEN** the newly displayed title SHALL be the current one

#### Scenario: Unresolved link is still usable
- **GIVEN** a reference whose title cannot be resolved
- **WHEN** the link is displayed
- **THEN** it SHALL be shown with its address and marked as unresolved
- **AND** it SHALL remain openable

### Requirement: Unreachable, deleted and forbidden are distinguishable

The system SHALL distinguish, for each link it fails to resolve, whether the
document platform was unavailable, the document no longer exists, or the viewer is
not permitted to see it, and SHALL report the distinguishing state on the link. A
link the viewer is not permitted to see SHALL disclose no title, no summary and no
other document content. No unresolvable link SHALL cause the asset, its
specification or the remainder of its links to fail to display.

#### Scenario: Service unavailable
- **GIVEN** the document platform is unreachable
- **WHEN** an asset with three linked documents is displayed
- **THEN** all three SHALL be listed as temporarily unresolvable
- **AND** the rest of the asset's specification SHALL display normally

#### Scenario: Deleted document
- **GIVEN** a linked document that has been deleted at the document platform
- **WHEN** the link is displayed
- **THEN** it SHALL be marked as no longer existing
- **AND** the reference SHALL remain in the specification until a person removes it

#### Scenario: Viewer not permitted
- **GIVEN** a linked document the viewer has not been granted access to
- **WHEN** the link is displayed
- **THEN** it SHALL be marked as not accessible to this viewer
- **AND** no title, summary or other content of that document SHALL be shown

#### Scenario: One broken link does not break the list
- **GIVEN** an asset with one readable link and one forbidden link
- **WHEN** the asset's links are listed
- **THEN** the readable link SHALL be shown resolved
- **AND** the forbidden link SHALL be shown in its state

### Requirement: Listing the documents linked to an asset

The system SHALL list, for a given asset, every document linked to it and every
document linked at project scope, each carrying its title where resolvable, its
scope, its state, who linked it and when. The order SHALL be deterministic and
SHALL NOT vary between calls for the same stored references.

#### Scenario: Deterministic ordering
- **GIVEN** an asset with several linked documents
- **WHEN** its links are listed twice without any change to the specification
- **THEN** both listings SHALL contain the same links in the same order

#### Scenario: Scope is visible
- **WHEN** an asset with both asset-scoped and project-scoped links is listed
- **THEN** each entry SHALL state which scope it came from

### Requirement: Creating a pre-titled document for an asset

A person SHALL be able to create a new long-form document for an asset from within
the system. The document SHALL be created at the document platform under that
person's own authority, pre-titled from the asset's identity, and the resulting
reference SHALL be linked to the asset in the same action. If the document is
created but the link cannot be written, the system SHALL report the failure and
name the created document so it is not lost. If the document cannot be created,
no link SHALL be written.

#### Scenario: One action produces a linked document
- **GIVEN** an asset named `mech_scout`
- **WHEN** a person creates a design document for it
- **THEN** a document SHALL exist at the document platform whose title identifies
  that asset
- **AND** the asset's specification SHALL contain a reference to it attributed to
  that person

#### Scenario: Creation refused leaves no link
- **GIVEN** a person without permission to create documents in the target workspace
- **WHEN** they attempt to create a design document for an asset
- **THEN** the attempt SHALL be refused with the reason
- **AND** the asset's specification SHALL be unchanged

#### Scenario: Link write failure names the created document
- **GIVEN** a document that was created successfully
- **WHEN** writing the reference into the specification fails
- **THEN** the failure SHALL be reported
- **AND** the report SHALL name the created document and its address

### Requirement: Checkable facts live in the specification, rationale lives in the document

The system SHALL treat the asset's `design` block and a linked document as
non-overlapping homes for different content: a statement that constrains art,
constrains code or is checkable by the validator belongs in the `design` block,
and prose rationale, exploration and discussion belong in the linked document. The
system SHALL NOT derive, extract, generate or pre-fill any specification field
from a linked document's contents, by any means including a language model, and
SHALL NOT treat a document's contents as a constraint on an export.

#### Scenario: No field is generated from a document
- **GIVEN** a linked document describing a socket in prose
- **WHEN** the link is created and the asset is displayed and compiled
- **THEN** no `design` field SHALL have been added or altered
- **AND** validation of an export SHALL be unaffected by that document's contents

#### Scenario: Guidance at the point of authoring
- **WHEN** a person is offered the choice of where to write a statement
- **THEN** the system SHALL state that constraining or checkable statements belong
  in the specification and that rationale belongs in the document

#### Scenario: Document contents are not constraints
- **GIVEN** a linked document stating a triangle budget in prose
- **WHEN** an export exceeding that number but within the specification's declared
  budget is validated
- **THEN** no violation SHALL be reported

### Requirement: A compiled specification carries the link, never the document

Compiling an asset's specification SHALL include its document links as bare
references exactly as authored, and SHALL NOT include any of a linked document's
body, title, summary or other resolved content. Compilation SHALL NOT contact the
document platform.

#### Scenario: Compiled output does not vary with platform reachability
- **GIVEN** an asset carrying document links
- **WHEN** it is compiled with the platform reachable and again with it unreachable
- **THEN** the two outputs SHALL be byte-identical

#### Scenario: Compilation is not blocked by the platform
- **GIVEN** the document platform is unreachable
- **WHEN** an asset's specification is compiled
- **THEN** compilation SHALL succeed
- **AND** each document link SHALL appear as its address

#### Scenario: No prose is compiled in
- **GIVEN** a linked document of several thousand words
- **WHEN** the asset's specification is compiled
- **THEN** the compiled output SHALL grow by at most the link's own line

### Requirement: Resolved titles and summaries are display-only cache

A title or summary resolved from the document platform SHALL live only in the
rebuildable index and SHALL NOT be written into a specification file or into the
compiled briefing, in any form, including as a labelled section.

#### Scenario: Resolved content never reaches authored or compiled artifacts
- **GIVEN** a resolved title and summary held for a document link
- **WHEN** the asset's specification file and its compiled briefing are examined
- **THEN** neither SHALL contain the resolved title or summary

### Requirement: Validation never contacts the document platform

Specification validation and export validation SHALL NOT contact the document
platform, SHALL NOT require it to be configured, and SHALL produce identical
results whether it is reachable or not. A document reference SHALL be checked only
for being well formed.

#### Scenario: Offline validation is unaffected
- **GIVEN** an asset carrying document links and no network access
- **WHEN** its export is validated
- **THEN** validation SHALL complete
- **AND** its report SHALL be identical to the report produced with the platform
  reachable

#### Scenario: Malformed reference is a specification violation
- **WHEN** a specification contains a document reference that is not well formed
- **THEN** specification linting SHALL report it
- **AND** the report SHALL name the offending reference

### Requirement: The integration degrades to absent

When the document platform is not configured, every capability of the system
unrelated to linked documents SHALL behave identically to a deployment where it is
configured. Document-linking features SHALL report themselves unavailable with the
reason, existing stored references SHALL still be listed and openable as plain
addresses, and no operation SHALL fail because the platform is absent.

#### Scenario: Unconfigured deployment works
- **GIVEN** no document platform configuration in the environment
- **WHEN** assets are browsed, specifications compiled and exports validated
- **THEN** all SHALL behave exactly as with the platform configured

#### Scenario: Creating a link reports unavailability
- **GIVEN** no document platform configuration in the environment
- **WHEN** a person attempts to create a design document for an asset
- **THEN** the feature SHALL report itself unavailable and name the reason
- **AND** no specification SHALL be modified

#### Scenario: Existing references survive
- **GIVEN** an asset carrying document references and no platform configuration
- **WHEN** the asset's links are listed
- **THEN** each reference SHALL be listed with its address and marked unresolved
