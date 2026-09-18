# Spec Delta

## Purpose

Specifies the two exits every annotation must take — promoted into a durable rule
or resolved as a transient issue — together with who may take each exit, the art
director's periodic pass over open feedback, and the guarantee that a briefing
read by a person or an agent carries standing rules and live issues only, never a
growing archive of settled arguments. This is the loop that turns recorded
disagreement into convergence, and it is the heart of the product.

## ADDED Requirements

### Requirement: Exactly two exits, and no third

An annotation SHALL leave the open state in exactly one of two ways: **promoted**,
meaning its content became a durable rule of the asset and the annotation is
retired, or **resolved**, meaning it was a specific transient issue that has been
addressed. The system SHALL NOT offer any other terminal state — no "won't fix",
no "archived", no "closed" — and SHALL NOT allow an annotation to be both. An
annotation whose conclusion is that no change is needed SHALL be recorded as
resolved with that conclusion as its closing text.

#### Scenario: Only two exits are offered
- **GIVEN** an open annotation
- **WHEN** the available exits for it are requested
- **THEN** exactly two SHALL be offered: promote and resolve

#### Scenario: A second exit is refused
- **GIVEN** an annotation that has been resolved
- **WHEN** it is promoted without first being reopened
- **THEN** the request SHALL be refused stating that the annotation is already resolved

### Requirement: Promotion writes a durable rule and retires the annotation atomically

Promoting an annotation SHALL require the promoter to state the durable rule text
and its destination, being either the asset's engineering `constraints` or its
`concept.silhouette_rules`. The rule SHALL be written into that destination and
the annotation SHALL be marked promoted and removed from the open set **in a
single operation**: the system SHALL NOT produce a state in which the rule exists
while the annotation is still open, or in which the annotation is retired while no
rule was written.

#### Scenario: Promotion lands the rule
- **GIVEN** an open annotation stating that the lens glow is always emissive
- **WHEN** an art director promotes it into `concept.silhouette_rules`
- **THEN** that rule SHALL appear among the asset's durable rules
- **AND** the annotation SHALL be marked promoted and SHALL NOT remain open

#### Scenario: Promotion with no destination refused
- **WHEN** a promotion is requested without naming a destination
- **THEN** the request SHALL be refused naming the two valid destinations
- **AND** the annotation SHALL remain open

#### Scenario: Failed write leaves nothing half-done
- **GIVEN** a promotion whose write to the repository fails
- **WHEN** the asset is read afterwards
- **THEN** the annotation SHALL still be open
- **AND** no partial rule SHALL appear in the asset's durable rules

### Requirement: Only an art director may promote

Promotion SHALL be permitted only to a person holding the art director role for
the project. Any other person SHALL be refused with a message naming the required
role, and the annotation SHALL remain open. Every other annotation operation —
creating, replying, editing one's own, resolving — SHALL remain available
independently of role.

#### Scenario: Artist attempting promotion refused
- **GIVEN** an open annotation and a person whose roles do not include art director
- **WHEN** that person promotes it
- **THEN** the request SHALL be refused naming the required role
- **AND** the annotation SHALL remain open

#### Scenario: Refusal does not remove other exits
- **GIVEN** a person who was refused promotion
- **WHEN** that person resolves the same annotation
- **THEN** the resolution SHALL succeed

### Requirement: Promotion is never available to an automated caller

Promotion SHALL NOT be invocable by an automated caller under any circumstances,
including when the person it acts for holds the art director role. The system
SHALL NOT expose promotion through any agent-facing surface in this or any future
version, and an attempt SHALL be refused stating that promotion is a person's act.

#### Scenario: Art director's agent refused
- **GIVEN** an automated caller acting on behalf of an art director
- **WHEN** it attempts to promote an annotation
- **THEN** the request SHALL be refused
- **AND** the asset's durable rules SHALL be unchanged

#### Scenario: Promotion is absent from the agent surface
- **WHEN** the operations available to an automated caller are enumerated
- **THEN** no operation that writes a durable rule SHALL be among them

### Requirement: A promotion is a reviewable, attributed change to the repository

A promotion SHALL result in a change to the asset's specification file in the game
repository that can be reviewed with ordinary version control tooling: a small,
legible difference adding the rule and retiring the annotation, attributed to the
person who promoted it and carrying a message naming the asset and the annotation
promoted. Promotion SHALL NOT be recorded only in a derived index.

#### Scenario: Promotion is visible in history
- **WHEN** an art director promotes an annotation
- **THEN** the repository history SHALL contain a change attributed to that person
- **AND** that change SHALL show the added rule and the retired annotation

#### Scenario: Index rebuild preserves the promotion
- **GIVEN** a promoted annotation and a rule written by that promotion
- **WHEN** every derived index is deleted and rebuilt from the repository
- **THEN** the rule SHALL still be present and the annotation SHALL still be retired

### Requirement: A promotion that would invalidate the specification is refused

Before a promoted rule is written, the resulting specification SHALL be checked
for structural validity, and a promotion producing an invalid specification SHALL
be refused with the violations that would result. The system SHALL NOT write a
specification file that its own validator rejects.

#### Scenario: Invalid resulting constraint refused
- **GIVEN** a promotion that would set a triangle budget below the first LOD's count
- **WHEN** the promotion is submitted
- **THEN** it SHALL be refused reporting that violation
- **AND** the specification file SHALL be unchanged

### Requirement: Resolution archives an issue and removes it from the briefing

Resolving an annotation SHALL mark it resolved, record who resolved it and when,
and exclude it from the asset's compiled briefing from that point on. A resolved
annotation SHALL remain removable from the specification file entirely, its
history preserved by version control rather than by accumulation. Resolution SHALL
be available to the annotation's author, to the asset's owner for the annotation's
discipline, and to an art director.

#### Scenario: Resolved annotation leaves the briefing
- **GIVEN** an asset with one open and one just-resolved annotation
- **WHEN** the asset's specification is compiled
- **THEN** the output SHALL contain the open annotation
- **AND** it SHALL NOT contain the resolved one

#### Scenario: An uninvolved person may not resolve
- **GIVEN** a person who is neither the author, nor a discipline owner of the asset, nor an art director
- **WHEN** they attempt to resolve the annotation
- **THEN** the request SHALL be refused
- **AND** the annotation SHALL remain open

### Requirement: The briefing never grows from settled annotations

The compiled briefing for an asset SHALL NOT grow as a consequence of annotations
being resolved. Resolving an annotation SHALL remove an open item and add nothing;
promoting one SHALL replace an open item with a rule. An asset that accumulates
and settles many annotations over time SHALL produce a briefing whose size is
governed by its rules and its currently open issues alone.

#### Scenario: Settling many issues does not inflate the briefing
- **GIVEN** an asset whose briefing is compiled with no open annotations
- **WHEN** twenty annotations are created and then all resolved
- **AND** the briefing is compiled again
- **THEN** the second output SHALL be identical to the first

#### Scenario: Promotion adds a rule, not a thread
- **GIVEN** an annotation with six replies that is promoted
- **WHEN** the briefing is compiled
- **THEN** it SHALL contain the promoted rule
- **AND** it SHALL NOT contain the annotation's text or any of its replies

### Requirement: Reopening is possible for a resolved issue and impossible for a rule

A resolved annotation SHALL be reopenable, returning it to the open state and to
the triage queue, with the reopening attributed. A promoted annotation SHALL NOT
be reopenable: its content is now a rule, and changing it SHALL be done by editing
that rule, which is an ordinary reviewable specification change.

#### Scenario: Reopening a resolved issue
- **GIVEN** a resolved annotation
- **WHEN** a person with resolution rights reopens it
- **THEN** it SHALL be open again and appear in the triage queue
- **AND** the reopening SHALL be attributed to that person

#### Scenario: Reopening a promotion refused
- **GIVEN** a promoted annotation
- **WHEN** reopening it is attempted
- **THEN** the request SHALL be refused stating that its content is now a rule

### Requirement: The triage queue surfaces recurring feedback for the periodic pass

The system SHALL provide, for a project, a queue of all open annotations across
its assets, filterable by kind, by asset and by discipline owner. For each
annotation the queue SHALL report how many other open annotations of the same kind
exist on the same asset and across the project, its reply count, and its age, and
SHALL order it by those counts before age, so that feedback repeating across a
project rises to the top as a promotion candidate. The queue SHALL be derivable
from the repository alone.

#### Scenario: Repeated feedback rises
- **GIVEN** an asset with four open `art-direction` annotations and another with one
- **WHEN** the project's triage queue is requested
- **THEN** annotations from the asset with four SHALL be ordered above the single one
- **AND** each entry SHALL report its same-kind counts, its reply count and its age

#### Scenario: Queue is filterable for a pass
- **GIVEN** a project with annotations of all three kinds
- **WHEN** the queue is requested filtered to `art-direction`
- **THEN** only `art-direction` annotations SHALL be returned

#### Scenario: Queue needs no derived store
- **GIVEN** every derived index has been deleted
- **WHEN** the triage queue is requested
- **THEN** it SHALL be produced from the repository

### Requirement: Triage behaves identically for both anchor forms

Promotion, resolution, reopening, queue membership and queue ordering SHALL
behave identically for an annotation carrying a 2D anchor and one carrying a 3D
anchor. The anchor form SHALL NOT affect who may take an exit, what a promotion
writes, or where an annotation appears in the queue.

#### Scenario: Same exit, either medium
- **GIVEN** one open annotation with a 2D anchor and one with a 3D anchor, of the same kind and age
- **WHEN** each is promoted by an art director into the same destination
- **THEN** both SHALL produce a rule in that destination and be retired
- **AND** neither outcome SHALL depend on the anchor form

#### Scenario: Mixed queue is ordered by the same signals
- **GIVEN** a project whose open annotations use both anchor forms
- **WHEN** the triage queue is requested
- **THEN** ordering SHALL be determined by the same counts and age for both forms
