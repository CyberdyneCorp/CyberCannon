# Spec Delta

## Purpose

The first artist-facing surface: an asset's concept views shown side by side with
pins placed on them, drawn with a pointer or a stylus, so that feedback is
attached to the exact place on the image it is about. Its only job in the system
is turning an input gesture into a durable anchor and presenting the threads that
already exist — the sheet decides nothing about kinds, permissions, threading or
triage, which are specified once and shared with the three-dimensional viewer.

## ADDED Requirements

### Requirement: The sheet presents an asset's views without inventing any

The model sheet SHALL present the views recorded for an asset, each identified by
the name the annotation anchors use, and SHALL present them at their stored
resolution or a scaled rendition of it. When an asset has no views, the sheet
SHALL say so and SHALL still present the asset's identity, status and existing
annotations. The sheet SHALL NOT generate, substitute or place a view the asset
does not have.

#### Scenario: Views listed by anchor name
- **GIVEN** an asset with views named `front`, `side` and `back`
- **WHEN** its model sheet is opened
- **THEN** all three views SHALL be presented, each identified by that name

#### Scenario: Asset with no views
- **GIVEN** an asset with no views recorded
- **WHEN** its model sheet is opened
- **THEN** the sheet SHALL state that the asset has no views
- **AND** it SHALL still present the asset's identity and status

### Requirement: The view's only output is an anchor

The sheet SHALL translate an input gesture over a view into a 2D anchor — the
view's name and a normalized coordinate within it — and SHALL contribute nothing
else to an annotation. Deciding the kind, who may act, how threads are ordered,
which annotations are shown for a filter, and what an exit does SHALL NOT be
determined by the sheet, and SHALL produce the same results here as on any other
surface presenting the same annotations.

#### Scenario: Placement yields an anchor and nothing more
- **WHEN** a pin is placed on a view
- **THEN** the sheet SHALL produce an anchor naming that view and a normalized coordinate
- **AND** the annotation's kind, author, attribution and state SHALL be determined
  by the same rules that apply on every other surface

#### Scenario: Filtering agrees across surfaces
- **GIVEN** an asset whose annotations are filtered to open `technical` items
- **WHEN** the same filter is applied on the sheet and on any other surface
- **THEN** both SHALL present the same set of annotations

### Requirement: Anchor coordinates are normalized and independent of presentation

A pin's coordinate SHALL be recorded normalized to the view's own image space, in
the range 0 to 1 on each axis, and SHALL NOT depend on the zoom level, the pan
offset, the size of the display area, the device pixel ratio, or the rendition
resolution at which the view was presented. Placing a pin and then re-presenting
it at any zoom, on any display, SHALL put it over the same feature of the image.

#### Scenario: Zoom does not move a pin
- **GIVEN** a pin placed over a specific feature of a view at one zoom level
- **WHEN** the view is zoomed, panned and the window resized
- **THEN** the pin SHALL remain over that same feature of the image

#### Scenario: Same coordinate on a different device
- **GIVEN** a pin recorded at a normalized coordinate
- **WHEN** the same view is opened on a display of a different size and pixel density
- **THEN** the pin SHALL appear at the same position relative to the image

#### Scenario: Round trip preserves the coordinate
- **WHEN** a pin is placed, stored, re-read and presented again without being moved
- **THEN** its recorded coordinate SHALL be unchanged

### Requirement: Placement outside the image is refused

An input gesture whose position falls outside the bounds of the view's image —
in the surrounding letterboxing, on the sheet background, or beyond the edge
during a drag — SHALL NOT create an annotation, and SHALL NOT be clamped to the
image edge. The sheet SHALL indicate that no pin was placed.

#### Scenario: Gesture on the background places nothing
- **WHEN** a placement gesture occurs outside the image area of every view
- **THEN** no annotation SHALL be created
- **AND** no coordinate SHALL be clamped to an edge

### Requirement: Pins are placed with a pointer or a stylus

The sheet SHALL accept pin placement from a mouse, a trackpad, a touch input and
a stylus, producing an identical anchor for an identical position
regardless of which was used. On a tablet where a stylus is in use, a stylus
gesture SHALL place or draw while a finger gesture SHALL pan and zoom, so that
the hand resting on the display does not create annotations.

#### Scenario: Pencil and mouse agree
- **GIVEN** the same position over a view
- **WHEN** a pin is placed there with a mouse and again with a stylus
- **THEN** both SHALL produce the same normalized coordinate

#### Scenario: Finger navigates, stylus annotates
- **GIVEN** a tablet session in which a stylus has been used
- **WHEN** a finger gesture drags across a view
- **THEN** the view SHALL pan
- **AND** no annotation SHALL be created

### Requirement: Selecting a pin opens its thread

Selecting a pin SHALL present that annotation's thread — its text, its kind, its
attribution, its state and its replies in order — and SHALL make the selected pin
visually distinguishable from the others. Exactly one annotation SHALL be
selected at a time, and selecting an annotation from the thread panel's list
SHALL highlight its pin on the view, including bringing the view containing it
into presentation.

#### Scenario: Pin to thread
- **WHEN** a pin is selected on a view
- **THEN** its annotation's text, kind, attribution, state and replies SHALL be presented
- **AND** the selected pin SHALL be distinguishable from the unselected ones

#### Scenario: Thread to pin across views
- **GIVEN** an annotation anchored to a view that is not currently in focus
- **WHEN** it is selected from the thread panel
- **THEN** that view SHALL be brought into presentation with its pin highlighted

### Requirement: Pins are filterable by kind and by state

The sheet SHALL filter the pins presented over the views by annotation kind
(`art-direction`, `technical`, `design`) and by state (open or resolved), with
the two filters combining. A filtered-out annotation SHALL be hidden from the
views and from the thread list but SHALL NOT be altered, and the sheet SHALL
report how many annotations the current filter is hiding.

#### Scenario: Combined filter
- **GIVEN** an asset with open and resolved annotations of all three kinds
- **WHEN** the filter is set to open `art-direction`
- **THEN** only open `art-direction` pins SHALL be presented
- **AND** the number of hidden annotations SHALL be reported

#### Scenario: Filtering changes nothing durable
- **GIVEN** any filter has been applied
- **WHEN** the asset's specification is read from the repository
- **THEN** every annotation SHALL be unchanged

#### Scenario: Default presentation shows open work
- **WHEN** a model sheet is opened with no filter chosen
- **THEN** open annotations of every kind SHALL be presented

### Requirement: Overlapping and orphaned annotations remain reachable

Annotations whose pins fall close enough together to overlap SHALL each remain
individually selectable. Annotations that are orphaned — anchored to a view the
asset no longer has — SHALL be listed in the thread panel with the reason they
cannot be shown, and SHALL NOT be drawn over any view.

#### Scenario: Two pins at nearly the same coordinate
- **GIVEN** two annotations anchored within a pin's width of each other
- **WHEN** the view is presented
- **THEN** each annotation SHALL be individually selectable

#### Scenario: Orphans are visible but not placed
- **GIVEN** an annotation anchored to a view that has been removed
- **WHEN** the model sheet is opened
- **THEN** the annotation SHALL be listed with its reason
- **AND** no pin for it SHALL be drawn over any remaining view

### Requirement: A freehand scribble is a pointing gesture, not a painting tool

The sheet SHALL allow freehand strokes to be drawn over a view while composing
or editing an annotation, recorded in the same normalized image space as pins and
attached to that annotation. The most recent stroke SHALL be undoable and the
whole scribble SHALL be discardable before the annotation is saved. The sheet
SHALL NOT offer brush selection, stroke width or colour choice, layers, opacity,
erasing of parts of a stroke, or any operation that modifies the view image.

#### Scenario: Scribble is attached to its annotation
- **GIVEN** an annotation being composed with two strokes drawn over a view
- **WHEN** it is saved
- **THEN** the strokes SHALL be recorded with that annotation in normalized coordinates

#### Scenario: Discarding before saving leaves nothing
- **GIVEN** strokes drawn while composing an annotation
- **WHEN** the composition is cancelled
- **THEN** no strokes and no annotation SHALL be recorded

#### Scenario: Strokes scale with the view
- **GIVEN** an annotation carrying freehand strokes
- **WHEN** the view is zoomed
- **THEN** the strokes SHALL remain over the same features of the image

### Requirement: The thread panel offers only the exits the person may take

The thread panel SHALL present the actions available for the selected annotation
to the person using it — replying, editing or deleting their own contribution,
resolving, and promoting — offering promotion only to a person permitted to
promote, and the panel SHALL state which destination a promotion will write to
before it is submitted. Hiding an action SHALL NOT be the only enforcement: a
submitted action the person may not take SHALL be refused by the system.

#### Scenario: Promotion is not offered to a non-director
- **GIVEN** a person whose roles do not include art director
- **WHEN** they select an open annotation
- **THEN** no promotion action SHALL be offered

#### Scenario: Hidden is not the same as forbidden
- **GIVEN** the same person submits a promotion regardless
- **WHEN** the request reaches the system
- **THEN** it SHALL be refused
- **AND** the annotation SHALL remain open

### Requirement: A placed pin appears at once and a failed write is undone visibly

A pin SHALL appear on the view as soon as it is placed, without waiting for the
write to complete. When the write fails, the pin SHALL be removed from the view
and the failure SHALL be reported with the text preserved so it can be retried,
and the sheet SHALL NOT present an annotation that was not durably recorded once
the failure is known.

#### Scenario: Immediate feedback
- **WHEN** a pin is placed
- **THEN** it SHALL be presented immediately

#### Scenario: Failed write removes the pin
- **GIVEN** a placed pin whose write to the repository fails
- **WHEN** the failure is known
- **THEN** the pin SHALL be removed from the view
- **AND** the failure SHALL be reported with the entered text preserved

#### Scenario: Reload agrees with the repository
- **GIVEN** a sequence of placements of which one failed
- **WHEN** the model sheet is reloaded
- **THEN** the pins presented SHALL be exactly those recorded in the repository
