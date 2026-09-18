# Spec Delta

## Purpose

Specifies how feedback on an asset is created and maintained: attaching an
annotation to a durable anchor, giving it a kind, arguing about it in a thread,
correcting or withdrawing one's own contribution, and recording who said it — the
person, and the agent when one acted on their behalf. Everything here except the
construction of the anchor itself holds identically for a two-dimensional and a
three-dimensional anchor, so that a second medium costs a renderer and not a
second annotation system.

## ADDED Requirements

### Requirement: An annotation is created against exactly one durable anchor

Creating an annotation SHALL require exactly one anchor, being either a **2D
anchor** naming a view of the asset and a normalized coordinate within it, or a
**3D anchor** whose durable key is a named mesh part. A creation request carrying
no anchor, both anchor forms, or an anchor naming a view or part that the asset
does not have SHALL be refused with a message naming the missing subject, and
SHALL NOT create an annotation.

#### Scenario: Annotation created on a view
- **GIVEN** an asset with a view named `front`
- **WHEN** an annotation is created against that view at a normalized coordinate
- **THEN** the annotation SHALL be recorded against the asset with that anchor
- **AND** it SHALL be retrievable among the asset's annotations

#### Scenario: Anchorless annotation refused
- **WHEN** an annotation is created with no anchor
- **THEN** the request SHALL be refused
- **AND** no annotation SHALL be recorded for the asset

#### Scenario: Anchor naming an absent subject refused
- **GIVEN** an asset with views `front` and `side`
- **WHEN** an annotation is created against a view named `three_quarter`
- **THEN** the request SHALL be refused naming `three_quarter` as absent
- **AND** the system SHALL NOT attach the annotation to another view

### Requirement: Kind is required and closed

Every annotation SHALL declare a `kind` of `art-direction`, `technical` or
`design`. A creation request with no kind or a kind outside that set SHALL be
refused naming the allowed values. The kind SHALL be recorded with the
annotation and SHALL be available for filtering and for triage without reading
the annotation's text.

#### Scenario: Unknown kind refused
- **WHEN** an annotation is created with kind `nitpick`
- **THEN** the request SHALL be refused naming `art-direction`, `technical` and `design`

#### Scenario: Kind is machine-readable
- **GIVEN** an asset with annotations of all three kinds
- **WHEN** its annotations are listed filtered to `technical`
- **THEN** only the `technical` annotations SHALL be returned

### Requirement: A new annotation is open and untriaged

An annotation SHALL be created in the **open** state, meaning neither resolved
nor promoted. An open annotation SHALL appear in the asset's compiled briefing as
an open issue, and SHALL appear in the project's triage queue until it takes one
of its two exits.

#### Scenario: New annotation reaches the briefing
- **WHEN** an annotation is created on an asset
- **AND** that asset's specification is compiled
- **THEN** the annotation SHALL appear among the asset's open issues

#### Scenario: New annotation is awaiting triage
- **WHEN** an annotation is created on an asset of a project
- **THEN** it SHALL appear in that project's list of annotations awaiting triage

### Requirement: Replies form a thread and carry no anchor of their own

An annotation SHALL accept replies, forming an ordered thread. A reply SHALL
carry its own author, its own attribution and its own creation time, and SHALL
NOT carry an anchor, a kind or a resolution state of its own — a thread has one
anchor and one exit, which are the root annotation's. Replies SHALL be presented
in creation order.

#### Scenario: Reply inherits the thread's anchor
- **GIVEN** an open annotation anchored to part `SM_MechScout_Shoulder_L`
- **WHEN** a second person replies to it
- **THEN** the reply SHALL belong to that thread
- **AND** the reply SHALL NOT be independently anchored or independently resolvable

#### Scenario: Thread order is stable
- **GIVEN** an annotation with three replies created in a known order
- **WHEN** the thread is read twice
- **THEN** both readings SHALL present the replies in that same order

### Requirement: A person may edit and withdraw only their own contribution

The author of an annotation or a reply SHALL be able to edit its text and to
delete it. A person SHALL NOT be able to edit another person's text, and an edit
SHALL NOT change the contribution's author or its recorded attribution. An
annotation that has replies SHALL NOT be deletable — it SHALL be resolved or
promoted instead — so that a thread always ends in one of its two exits.

#### Scenario: Editing another person's annotation refused
- **GIVEN** an annotation authored by one person
- **WHEN** a different person attempts to edit its text
- **THEN** the request SHALL be refused
- **AND** the recorded text SHALL be unchanged

#### Scenario: Deleting a thread with replies refused
- **GIVEN** an annotation that has at least one reply
- **WHEN** its author attempts to delete it
- **THEN** the request SHALL be refused stating that it may be resolved or promoted
- **AND** the thread SHALL remain readable

#### Scenario: Deleting an untouched annotation succeeds
- **GIVEN** an annotation with no replies
- **WHEN** its author deletes it
- **THEN** it SHALL no longer appear among the asset's annotations
- **AND** it SHALL NOT appear in the compiled briefing

### Requirement: Re-anchoring is explicit, recorded, and the author's act

The author of an annotation SHALL be able to move it to a different anchor of the
same form, and the annotation SHALL record that it was moved. The system SHALL
NOT change an annotation's anchor as a side effect of any other operation,
including editing its text, replying to it, re-importing a view, or re-exporting
a mesh.

#### Scenario: Text edit leaves the anchor untouched
- **GIVEN** an annotation anchored at a normalized coordinate within a view
- **WHEN** its author edits only its text
- **THEN** the anchor SHALL be unchanged

#### Scenario: Move is attributed and visible
- **WHEN** an author moves their annotation to a different coordinate in the same view
- **THEN** the annotation SHALL record that it was moved and by whom

### Requirement: Attribution names the person, and the agent when one acted

Every annotation and every reply SHALL record the person responsible for it, and
SHALL additionally record the agent when an automated caller acted on that
person's behalf, presented so that both are visible — for example "rafa, via
blender-agent". The acting identity SHALL be derived from the credential the
request was made with and SHALL NEVER be taken from a request parameter, a tool
argument or a field in the submitted content. A contribution that cannot be
attributed to a person SHALL be refused rather than recorded anonymously.

#### Scenario: Agent-originated annotation names both
- **GIVEN** an automated caller acting on behalf of a person
- **WHEN** it creates an annotation
- **THEN** the annotation SHALL name that person as responsible
- **AND** it SHALL also name the agent that acted

#### Scenario: Submitted author field is ignored
- **GIVEN** a credential resolving to one person
- **WHEN** a creation request declares a different person as its author
- **THEN** the annotation SHALL be attributed to the person the credential resolves to

#### Scenario: Unattributable contribution refused
- **WHEN** a creation request cannot be resolved to a person
- **THEN** it SHALL be refused
- **AND** no annotation SHALL be recorded

### Requirement: Anyone with project write access may annotate, regardless of discipline

Creating an annotation, replying to one, and resolving one's own SHALL be
available to any person with write access to the project, independent of their
role. No discipline SHALL be required in order to raise feedback of any kind: an
engineer may raise an `art-direction` annotation and an artist may raise a
`technical` one.

#### Scenario: Engineer raises art direction feedback
- **GIVEN** a person whose only role is engineering
- **WHEN** they create an annotation of kind `art-direction`
- **THEN** the annotation SHALL be created normally

#### Scenario: Read-only person refused
- **GIVEN** a person with read access but not write access to the project
- **WHEN** they attempt to create an annotation
- **THEN** the request SHALL be refused
- **AND** reading the asset's annotations SHALL still succeed for them

### Requirement: Orphaned annotations remain usable and are never silently re-anchored

When an annotation's anchored subject no longer exists — a view removed or
replaced, or a mesh part renamed or deleted — the annotation SHALL be reported as
orphaned. An orphaned annotation SHALL remain readable, repliable and triageable,
and SHALL be excluded from the pins presented over any view or mesh until a
person re-anchors it. The system SHALL NOT attach an orphaned annotation to a
different view, coordinate or part on its own.

#### Scenario: Removed view orphans its annotations
- **GIVEN** annotations anchored to a view named `back`
- **WHEN** that view is removed from the asset
- **THEN** those annotations SHALL be reported as orphaned
- **AND** they SHALL NOT be displayed over any remaining view

#### Scenario: Orphan can still be resolved
- **GIVEN** an orphaned annotation
- **WHEN** it is resolved or promoted
- **THEN** that exit SHALL be recorded normally

### Requirement: Annotations and threads are durable in the repository

An annotation, its replies, its attribution and its anchor SHALL be recorded in
the asset's specification in the game repository. No annotation SHALL exist only
in a derived index, cache or database, and deleting every derived store and
re-reading the repository SHALL restore every annotation and every thread
unchanged.

#### Scenario: Index rebuild loses nothing
- **GIVEN** an asset with open and replied-to annotations
- **WHEN** every derived index is deleted and rebuilt from the repository
- **THEN** every annotation, reply, author and anchor SHALL be identical to before

#### Scenario: Annotation is visible in version control
- **WHEN** an annotation is created through any surface
- **THEN** the asset's specification file in the repository SHALL contain it
- **AND** the change SHALL be attributable to the person responsible for it

### Requirement: Freehand marks belong to the annotation, not to the image

An annotation MAY carry freehand marks: one or more strokes recorded as ordered
sequences of coordinates normalized to the anchored view's own image space. Marks
SHALL be stored as part of the annotation and SHALL disappear with it when it is
resolved, promoted or deleted. The system SHALL NOT modify, overwrite or produce
a flattened copy of the underlying view image, and SHALL NOT record marks as
pixels.

#### Scenario: Marks travel with the annotation
- **GIVEN** an annotation carrying two freehand strokes
- **WHEN** the annotation is resolved
- **THEN** the strokes SHALL no longer be presented over the view

#### Scenario: Source image untouched
- **GIVEN** a view image of an asset
- **WHEN** freehand marks are drawn over it and saved
- **THEN** the stored view image SHALL be byte-identical to before

### Requirement: Authoring behaviour is identical for both anchor forms

Creating, replying, editing, deleting, attributing, listing, filtering and
orphaning SHALL behave identically whether an annotation carries a 2D or a 3D
anchor. The only behaviour permitted to differ between the two forms is the
construction of the anchor itself and the presentation of its position.

#### Scenario: Same operations, same outcomes across media
- **GIVEN** one annotation with a 2D anchor and one with a 3D anchor, otherwise identical
- **WHEN** the same sequence of reply, edit and filter operations is applied to each
- **THEN** the resulting state of both SHALL differ only in their anchors

#### Scenario: A mixed list is uniform
- **GIVEN** an asset carrying annotations of both anchor forms
- **WHEN** its annotations are listed filtered by kind and open state
- **THEN** both forms SHALL be returned by the same filter with the same fields present
