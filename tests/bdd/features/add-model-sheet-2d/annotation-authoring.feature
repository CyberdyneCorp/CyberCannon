# Generated from openspec/changes/add-model-sheet-2d/specs/annotation-authoring/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-model-sheet-2d @capability:annotation-authoring @spec:openspec/changes/add-model-sheet-2d/specs/annotation-authoring/spec.md
Feature: annotation-authoring

  Rule: An annotation is created against exactly one durable anchor

    Scenario: Annotation created on a view
      Given an asset with a view named `front`
      When an annotation is created against that view at a normalized coordinate
      Then the annotation SHALL be recorded against the asset with that anchor
      And it SHALL be retrievable among the asset's annotations

    Scenario: Anchorless annotation refused
      When an annotation is created with no anchor
      Then the request SHALL be refused
      And no annotation SHALL be recorded for the asset

    Scenario: Anchor naming an absent subject refused
      Given an asset with views `front` and `side`
      When an annotation is created against a view named `three_quarter`
      Then the request SHALL be refused naming `three_quarter` as absent
      And the system SHALL NOT attach the annotation to another view

  Rule: Kind is required and closed

    Scenario: Unknown kind refused
      When an annotation is created with kind `nitpick`
      Then the request SHALL be refused naming `art-direction`, `technical` and `design`

    Scenario: Kind is machine-readable
      Given an asset with annotations of all three kinds
      When its annotations are listed filtered to `technical`
      Then only the `technical` annotations SHALL be returned

  Rule: A new annotation is open and untriaged

    Scenario: New annotation reaches the briefing
      When an annotation is created on an asset
      And that asset's specification is compiled
      Then the annotation SHALL appear among the asset's open issues

    Scenario: New annotation is awaiting triage
      When an annotation is created on an asset of a project
      Then it SHALL appear in that project's list of annotations awaiting triage

  Rule: Replies form a thread and carry no anchor of their own

    Scenario: Reply inherits the thread's anchor
      Given an open annotation anchored to part `SM_MechScout_Shoulder_L`
      When a second person replies to it
      Then the reply SHALL belong to that thread
      And the reply SHALL NOT be independently anchored or independently resolvable

    Scenario: Thread order is stable
      Given an annotation with three replies created in a known order
      When the thread is read twice
      Then both readings SHALL present the replies in that same order

  Rule: A person may edit and withdraw only their own contribution

    Scenario: Editing another person's annotation refused
      Given an annotation authored by one person
      When a different person attempts to edit its text
      Then the request SHALL be refused
      And the recorded text SHALL be unchanged

    Scenario: Deleting a thread with replies refused
      Given an annotation that has at least one reply
      When its author attempts to delete it
      Then the request SHALL be refused stating that it may be resolved or promoted
      And the thread SHALL remain readable

    Scenario: Deleting an untouched annotation succeeds
      Given an annotation with no replies
      When its author deletes it
      Then it SHALL no longer appear among the asset's annotations
      And it SHALL NOT appear in the compiled briefing

  Rule: Re-anchoring is explicit, recorded, and the author's act

    Scenario: Text edit leaves the anchor untouched
      Given an annotation anchored at a normalized coordinate within a view
      When its author edits only its text
      Then the anchor SHALL be unchanged

    Scenario: Move is attributed and visible
      When an author moves their annotation to a different coordinate in the same view
      Then the annotation SHALL record that it was moved and by whom

  Rule: Attribution names the person, and the agent when one acted

    Scenario: Agent-originated annotation names both
      Given an automated caller acting on behalf of a person
      When it creates an annotation
      Then the annotation SHALL name that person as responsible
      And it SHALL also name the agent that acted

    Scenario: Submitted author field is ignored
      Given a credential resolving to one person
      When a creation request declares a different person as its author
      Then the annotation SHALL be attributed to the person the credential resolves to

    Scenario: Unattributable contribution refused
      When a creation request cannot be resolved to a person
      Then it SHALL be refused
      And no annotation SHALL be recorded

  Rule: Anyone with project write access may annotate, regardless of discipline

    Scenario: Engineer raises art direction feedback
      Given a person whose only role is engineering
      When they create an annotation of kind `art-direction`
      Then the annotation SHALL be created normally

    Scenario: Read-only person refused
      Given a person with read access but not write access to the project
      When they attempt to create an annotation
      Then the request SHALL be refused
      And reading the asset's annotations SHALL still succeed for them

  Rule: Orphaned annotations remain usable and are never silently re-anchored

    Scenario: Removed view orphans its annotations
      Given annotations anchored to a view named `back`
      When that view is removed from the asset
      Then those annotations SHALL be reported as orphaned
      And they SHALL NOT be displayed over any remaining view

    Scenario: Orphan can still be resolved
      Given an orphaned annotation
      When it is resolved or promoted
      Then that exit SHALL be recorded normally

  Rule: Annotations and threads are durable in the repository

    Scenario: Index rebuild loses nothing
      Given an asset with open and replied-to annotations
      When every derived index is deleted and rebuilt from the repository
      Then every annotation, reply, author and anchor SHALL be identical to before

    Scenario: Annotation is visible in version control
      When an annotation is created through any surface
      Then the asset's specification file in the repository SHALL contain it
      And the change SHALL be attributable to the person responsible for it

  Rule: Freehand marks belong to the annotation, not to the image

    Scenario: Marks travel with the annotation
      Given an annotation carrying two freehand strokes
      When the annotation is resolved
      Then the strokes SHALL no longer be presented over the view

    Scenario: Source image untouched
      Given a view image of an asset
      When freehand marks are drawn over it and saved
      Then the stored view image SHALL be byte-identical to before

  Rule: Authoring behaviour is identical for both anchor forms

    Scenario: Same operations, same outcomes across media
      Given one annotation with a 2D anchor and one with a 3D anchor, otherwise identical
      When the same sequence of reply, edit and filter operations is applied to each
      Then the resulting state of both SHALL differ only in their anchors

    Scenario: A mixed list is uniform
      Given an asset carrying annotations of both anchor forms
      When its annotations are listed filtered by kind and open state
      Then both forms SHALL be returned by the same filter with the same fields present
