# Generated from openspec/changes/add-model-sheet-2d/specs/annotation-triage/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-model-sheet-2d @capability:annotation-triage @spec:openspec/changes/add-model-sheet-2d/specs/annotation-triage/spec.md
Feature: annotation-triage

  Rule: Exactly two exits, and no third

    Scenario: Only two exits are offered
      Given an open annotation
      When the available exits for it are requested
      Then exactly two SHALL be offered: promote and resolve

    Scenario: A second exit is refused
      Given an annotation that has been resolved
      When it is promoted without first being reopened
      Then the request SHALL be refused stating that the annotation is already resolved

  Rule: Promotion writes a durable rule and retires the annotation atomically

    Scenario: Promotion lands the rule
      Given an open annotation stating that the lens glow is always emissive
      When an art director promotes it into `concept.silhouette_rules`
      Then that rule SHALL appear among the asset's durable rules
      And the annotation SHALL be marked promoted and SHALL NOT remain open

    Scenario: Promotion with no destination refused
      When a promotion is requested without naming a destination
      Then the request SHALL be refused naming the two valid destinations
      And the annotation SHALL remain open

    Scenario: Failed write leaves nothing half-done
      Given a promotion whose write to the repository fails
      When the asset is read afterwards
      Then the annotation SHALL still be open
      And no partial rule SHALL appear in the asset's durable rules

  Rule: Only an art director may promote

    Scenario: Artist attempting promotion refused
      Given an open annotation and a person whose roles do not include art director
      When that person promotes it
      Then the request SHALL be refused naming the required role
      And the annotation SHALL remain open

    Scenario: Refusal does not remove other exits
      Given a person who was refused promotion
      When that person resolves the same annotation
      Then the resolution SHALL succeed

  Rule: Promotion is never available to an automated caller

    Scenario: Art director's agent refused
      Given an automated caller acting on behalf of an art director
      When it attempts to promote an annotation
      Then the request SHALL be refused
      And the asset's durable rules SHALL be unchanged

    Scenario: Promotion is absent from the agent surface
      When the operations available to an automated caller are enumerated
      Then no operation that writes a durable rule SHALL be among them

  Rule: A promotion is a reviewable, attributed change to the repository

    Scenario: Promotion is visible in history
      When an art director promotes an annotation
      Then the repository history SHALL contain a change attributed to that person
      And that change SHALL show the added rule and the retired annotation

    Scenario: Index rebuild preserves the promotion
      Given a promoted annotation and a rule written by that promotion
      When every derived index is deleted and rebuilt from the repository
      Then the rule SHALL still be present and the annotation SHALL still be retired

  Rule: A promotion that would invalidate the specification is refused

    Scenario: Invalid resulting constraint refused
      Given a promotion that would set a triangle budget below the first LOD's count
      When the promotion is submitted
      Then it SHALL be refused reporting that violation
      And the specification file SHALL be unchanged

  Rule: Resolution archives an issue and removes it from the briefing

    Scenario: Resolved annotation leaves the briefing
      Given an asset with one open and one just-resolved annotation
      When the asset's specification is compiled
      Then the output SHALL contain the open annotation
      And it SHALL NOT contain the resolved one

    Scenario: An uninvolved person may not resolve
      Given a person who is neither the author, nor a discipline owner of the asset, nor an art director
      When they attempt to resolve the annotation
      Then the request SHALL be refused
      And the annotation SHALL remain open

  Rule: The briefing never grows from settled annotations

    Scenario: Settling many issues does not inflate the briefing
      Given an asset whose briefing is compiled with no open annotations
      When twenty annotations are created and then all resolved
      And the briefing is compiled again
      Then the second output SHALL be identical to the first

    Scenario: Promotion adds a rule, not a thread
      Given an annotation with six replies that is promoted
      When the briefing is compiled
      Then it SHALL contain the promoted rule
      And it SHALL NOT contain the annotation's text or any of its replies

  Rule: Reopening is possible for a resolved issue and impossible for a rule

    Scenario: Reopening a resolved issue
      Given a resolved annotation
      When a person with resolution rights reopens it
      Then it SHALL be open again and appear in the triage queue
      And the reopening SHALL be attributed to that person

    Scenario: Reopening a promotion refused
      Given a promoted annotation
      When reopening it is attempted
      Then the request SHALL be refused stating that its content is now a rule

  Rule: The triage queue surfaces recurring feedback for the periodic pass

    Scenario: Repeated feedback rises
      Given an asset with four open `art-direction` annotations and another with one
      When the project's triage queue is requested
      Then annotations from the asset with four SHALL be ordered above the single one
      And each entry SHALL report its same-kind counts, its reply count and its age

    Scenario: Queue is filterable for a pass
      Given a project with annotations of all three kinds
      When the queue is requested filtered to `art-direction`
      Then only `art-direction` annotations SHALL be returned

    Scenario: Queue needs no derived store
      Given every derived index has been deleted
      When the triage queue is requested
      Then it SHALL be produced from the repository

  Rule: Triage behaves identically for both anchor forms

    Scenario: Same exit, either medium
      Given one open annotation with a 2D anchor and one with a 3D anchor, of the same kind and age
      When each is promoted by an art director into the same destination
      Then both SHALL produce a rule in that destination and be retired
      And neither outcome SHALL depend on the anchor form

    Scenario: Mixed queue is ordered by the same signals
      Given a project whose open annotations use both anchor forms
      When the triage queue is requested
      Then ordering SHALL be determined by the same counts and age for both forms
