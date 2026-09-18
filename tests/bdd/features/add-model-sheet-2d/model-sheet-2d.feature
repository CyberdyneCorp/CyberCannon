# Generated from openspec/changes/add-model-sheet-2d/specs/model-sheet-2d/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-model-sheet-2d @capability:model-sheet-2d @spec:openspec/changes/add-model-sheet-2d/specs/model-sheet-2d/spec.md
Feature: model-sheet-2d

  Rule: The sheet presents an asset's views without inventing any

    Scenario: Views listed by anchor name
      Given an asset with views named `front`, `side` and `back`
      When its model sheet is opened
      Then all three views SHALL be presented, each identified by that name

    Scenario: Asset with no views
      Given an asset with no views recorded
      When its model sheet is opened
      Then the sheet SHALL state that the asset has no views
      And it SHALL still present the asset's identity and status

  Rule: The view's only output is an anchor

    Scenario: Placement yields an anchor and nothing more
      When a pin is placed on a view
      Then the sheet SHALL produce an anchor naming that view and a normalized coordinate
      And the annotation's kind, author, attribution and state SHALL be determined by the same rules that apply on every other surface

    Scenario: Filtering agrees across surfaces
      Given an asset whose annotations are filtered to open `technical` items
      When the same filter is applied on the sheet and on any other surface
      Then both SHALL present the same set of annotations

  Rule: Anchor coordinates are normalized and independent of presentation

    Scenario: Zoom does not move a pin
      Given a pin placed over a specific feature of a view at one zoom level
      When the view is zoomed, panned and the window resized
      Then the pin SHALL remain over that same feature of the image

    Scenario: Same coordinate on a different device
      Given a pin recorded at a normalized coordinate
      When the same view is opened on a display of a different size and pixel density
      Then the pin SHALL appear at the same position relative to the image

    Scenario: Round trip preserves the coordinate
      When a pin is placed, stored, re-read and presented again without being moved
      Then its recorded coordinate SHALL be unchanged

  Rule: Placement outside the image is refused

    Scenario: Gesture on the background places nothing
      When a placement gesture occurs outside the image area of every view
      Then no annotation SHALL be created
      And no coordinate SHALL be clamped to an edge

  Rule: Pins are placed with a pointer or a stylus

    Scenario: Pencil and mouse agree
      Given the same position over a view
      When a pin is placed there with a mouse and again with a stylus
      Then both SHALL produce the same normalized coordinate

    Scenario: Finger navigates, stylus annotates
      Given a tablet session in which a stylus has been used
      When a finger gesture drags across a view
      Then the view SHALL pan
      And no annotation SHALL be created

  Rule: Selecting a pin opens its thread

    Scenario: Pin to thread
      When a pin is selected on a view
      Then its annotation's text, kind, attribution, state and replies SHALL be presented
      And the selected pin SHALL be distinguishable from the unselected ones

    Scenario: Thread to pin across views
      Given an annotation anchored to a view that is not currently in focus
      When it is selected from the thread panel
      Then that view SHALL be brought into presentation with its pin highlighted

  Rule: Pins are filterable by kind and by state

    Scenario: Combined filter
      Given an asset with open and resolved annotations of all three kinds
      When the filter is set to open `art-direction`
      Then only open `art-direction` pins SHALL be presented
      And the number of hidden annotations SHALL be reported

    Scenario: Filtering changes nothing durable
      Given any filter has been applied
      When the asset's specification is read from the repository
      Then every annotation SHALL be unchanged

    Scenario: Default presentation shows open work
      When a model sheet is opened with no filter chosen
      Then open annotations of every kind SHALL be presented

  Rule: Overlapping and orphaned annotations remain reachable

    Scenario: Two pins at nearly the same coordinate
      Given two annotations anchored within a pin's width of each other
      When the view is presented
      Then each annotation SHALL be individually selectable

    Scenario: Orphans are visible but not placed
      Given an annotation anchored to a view that has been removed
      When the model sheet is opened
      Then the annotation SHALL be listed with its reason
      And no pin for it SHALL be drawn over any remaining view

  Rule: A freehand scribble is a pointing gesture, not a painting tool

    Scenario: Scribble is attached to its annotation
      Given an annotation being composed with two strokes drawn over a view
      When it is saved
      Then the strokes SHALL be recorded with that annotation in normalized coordinates

    Scenario: Discarding before saving leaves nothing
      Given strokes drawn while composing an annotation
      When the composition is cancelled
      Then no strokes and no annotation SHALL be recorded

    Scenario: Strokes scale with the view
      Given an annotation carrying freehand strokes
      When the view is zoomed
      Then the strokes SHALL remain over the same features of the image

  Rule: The thread panel offers only the exits the person may take

    Scenario: Promotion is not offered to a non-director
      Given a person whose roles do not include art director
      When they select an open annotation
      Then no promotion action SHALL be offered

    Scenario: Hidden is not the same as forbidden
      Given the same person submits a promotion regardless
      When the request reaches the system
      Then it SHALL be refused
      And the annotation SHALL remain open

  Rule: A placed pin appears at once and a failed write is undone visibly

    Scenario: Immediate feedback
      When a pin is placed
      Then it SHALL be presented immediately

    Scenario: Failed write removes the pin
      Given a placed pin whose write to the repository fails
      When the failure is known
      Then the pin SHALL be removed from the view
      And the failure SHALL be reported with the entered text preserved

    Scenario: Reload agrees with the repository
      Given a sequence of placements of which one failed
      When the model sheet is reloaded
      Then the pins presented SHALL be exactly those recorded in the repository
