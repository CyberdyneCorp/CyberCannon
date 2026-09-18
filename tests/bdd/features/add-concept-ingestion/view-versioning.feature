# Generated from openspec/changes/add-concept-ingestion/specs/view-versioning/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-concept-ingestion @capability:view-versioning @spec:openspec/changes/add-concept-ingestion/specs/view-versioning/spec.md
Feature: view-versioning

  Rule: Replacing a view creates a revision and destroys nothing

    Scenario: Three uploads, three revisions
      Given a `front` view that has been uploaded and then replaced twice
      When its revisions are listed
      Then three revisions SHALL be listed and each SHALL be retrievable

    Scenario: Removing a view keeps its history
      Given a view with two revisions
      When the view is removed
      Then both earlier revisions SHALL still be retrievable
      And the view SHALL be reported as removed rather than as never having existed

    Scenario: An identical re-upload is not a revision
      Given a view whose current revision has a given content hash
      When a byte-identical image is uploaded to the same slot
      Then no new revision SHALL be created
      And the result SHALL report the view as unchanged

  Rule: Listing a view's revisions

    Scenario: A revision list is complete and ordered
      Given a view with three revisions
      When its revisions are listed
      Then three entries SHALL be returned newest first
      And each SHALL carry an identifier, a person, a time and a content hash
      And exactly one SHALL be marked current

    Scenario: Revision identifiers are stable
      When the same view's revisions are listed twice with no intervening change
      Then both listings SHALL report the same identifiers for the same revisions

    Scenario: A removed view has no current revision
      Given a view that has been removed
      When its revisions are listed
      Then the earlier revisions SHALL be listed and none SHALL be marked current

  Rule: Retrieving a specific revision

    Scenario: A historical revision is labelled
      When a superseded revision is retrieved by its identifier
      Then its image SHALL be returned
      And it SHALL be labelled historical with its revision identifier

    Scenario: Unknown revision identifier
      When a revision identifier that does not belong to the view is requested
      Then an explicit not-found result naming the identifier SHALL be returned
      And the current revision SHALL NOT be returned in its place

  Rule: Comparing two revisions

    Scenario: Comparing a superseded revision with the current one
      Given a view with revisions `r1` and `r2` where `r2` is current
      When the two are compared
      Then both images SHALL be presented with their identifier, person, time, dimensions, byte size and content hash

    Scenario: Argument order does not change the presentation
      Given revisions `r1` and `r2` of one view
      When they are compared as `r2, r1` and again as `r1, r2`
      Then both comparisons SHALL present `r1` as the older revision

    Scenario: Comparing two historical revisions
      Given a view with three revisions of which the third is current
      When the first and second are compared
      Then the comparison SHALL be produced normally

    Scenario: Comparing a revision with itself
      When a revision is compared with itself
      Then the result SHALL report the two as identical

  Rule: Revision history is served from the repository alone

    Scenario: History survives a wiped mirror
      Given a view with three revisions and an emptied blob store
      When its revisions are listed and a superseded one is retrieved
      Then both SHALL succeed using the repository

  Rule: Incomplete history is reported, never presented as complete

    Scenario: Shallow working copy
      Given a working copy whose history is truncated
      When a view's revisions are listed
      Then the available revisions SHALL be listed
      And the result SHALL state that earlier revisions are unavailable and from which point

  Rule: Annotations on a replaced view are carried or orphaned, never silently moved

    Scenario: Same aspect ratio carries the pins
      Given a view with four annotations anchored to it
      When it is replaced by an image of the same aspect ratio
      Then all four annotations SHALL be marked carried
      And each SHALL still name the revision it was authored against

    Scenario: A different aspect ratio orphans the pins
      Given a view with four annotations anchored to it
      When it is replaced by an image of a different aspect ratio
      Then all four annotations SHALL be marked orphaned
      And none SHALL be displayed at a position on the new revision

    Scenario: The outcome is never silent
      When a view carrying annotations is replaced
      Then the result of the replacement SHALL state how many annotations were carried and how many were orphaned

    Scenario: An orphan can still be read against its own revision
      Given an orphaned annotation
      When it is opened
      Then the revision it was authored against SHALL be retrievable and its position on that revision SHALL be shown

  Rule: Orphaning is an anchor state, not an exit

    Scenario: Orphans still appear in the compiled briefing
      Given an asset with one orphaned open annotation
      When its briefing is compiled
      Then that annotation SHALL appear among the open issues

    Scenario: Replacement resolves nothing
      Given a view with three open annotations
      When it is replaced such that all three are orphaned
      Then all three SHALL still be open
      And none SHALL be recorded as promoted or resolved

  Rule: Re-anchoring an orphan is an explicit human action

    Scenario: A person re-anchors an orphan
      Given an orphaned annotation
      When a person re-anchors it to a position on the current revision
      Then it SHALL be marked carried against that revision
      And the person and time of re-anchoring SHALL be recorded
      And its text and its open state SHALL be unchanged

    Scenario: Nothing re-anchors itself
      Given an orphaned annotation and a view that is replaced again
      When no person re-anchors it
      Then it SHALL still be orphaned
