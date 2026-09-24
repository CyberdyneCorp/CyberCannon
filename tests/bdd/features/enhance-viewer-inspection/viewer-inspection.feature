# Generated from openspec/changes/enhance-viewer-inspection/specs/viewer-inspection/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:enhance-viewer-inspection @capability:viewer-inspection @spec:openspec/changes/enhance-viewer-inspection/specs/viewer-inspection/spec.md
Feature: viewer-inspection

  Rule: Camera gestures redraw the preview

    Scenario: Drag and zoom change the visible camera
      Given a loaded preview
      When a reviewer drags to orbit and zooms with the wheel or zoom buttons
      Then the viewport SHALL redraw to show the resulting camera view
      And Frame asset SHALL restore a view containing the whole preview

    Scenario: Navigation does not place an annotation
      Given a loaded preview and annotation placement is available
      When a reviewer drags to orbit or pan
      Then no new annotation SHALL be composed

  Rule: Source and preview geometry stay distinct

    Scenario: Decimated preview has fewer triangles
      Given a source export with 1,280 triangles and a preview with 320
      When the viewer displays inspection details
      Then it SHALL show 1,280 as source triangles and 320 as preview triangles

    Scenario: Preview has no vertex normals
      Given a loaded preview whose primitives have no vertex-normal attributes
      When the viewer displays inspection details
      Then it SHALL say that preview vertex normals are absent

  Rule: Texture and normal-map details reflect the source export

    Scenario: Embedded normal map has known dimensions
      Given a validated source export with an embedded 1024 by 1024 normal map
      When the viewer displays inspection details
      Then it SHALL identify the normal channel and show 1024 × 1024 pixels

    Scenario: Texture reference cannot be inspected
      Given a source export referring to an image whose dimensions are unavailable
      When the viewer displays inspection details
      Then it SHALL identify the texture channel and state that its dimensions are unavailable

    Scenario: Source export cannot be read
      Given a recorded preview whose source export cannot currently be inspected
      When the viewer opens
      Then the preview and annotations SHALL remain available
      And source texture details SHALL be stated as unavailable
