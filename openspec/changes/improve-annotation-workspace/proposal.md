# Proposal

## Why

The annotation composer does not identify its placement, and 3D notes are difficult to find by part while viewing the model. The 2D pins also expose only a single letter to assistive technology.

## What Changes

- Show the current image or model part in the shared annotation composer, with clear save readiness and pending feedback.
- Give each 2D pin a descriptive accessible name and show concise placement guidance next to the image.
- Add a compact list of 3D annotations by part beside the model, using the existing selection and view restoration behavior.

## Capabilities

### Modified Capabilities

- `model-sheet-2d`: Placement guidance and identifiable pins.
- `viewer-3d`: Part-aware annotation navigation.
- `annotation-authoring`: Context and save feedback in the shared composer.

## Impact

Web components, component/browser tests, and annotation interaction documentation. No API or data model changes.
