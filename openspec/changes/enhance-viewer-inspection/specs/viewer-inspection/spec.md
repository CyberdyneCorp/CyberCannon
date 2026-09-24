# Viewer inspection

## ADDED Requirements

### Requirement: Camera gestures redraw the preview

When a preview is loaded, the viewer SHALL redraw it during orbit, pan, and zoom gestures. It SHALL explain the available pointer and touch gestures beside the viewport and SHALL provide zoom-in, zoom-out, and frame-asset controls that work without a wheel. Camera navigation SHALL NOT change the asset or its annotations.

#### Scenario: Drag and zoom change the visible camera
- **GIVEN** a loaded preview
- **WHEN** a reviewer drags to orbit and zooms with the wheel or zoom buttons
- **THEN** the viewport SHALL redraw to show the resulting camera view
- **AND** Frame asset SHALL restore a view containing the whole preview

#### Scenario: Navigation does not place an annotation
- **GIVEN** a loaded preview and annotation placement is available
- **WHEN** a reviewer drags to orbit or pan
- **THEN** no new annotation SHALL be composed

### Requirement: Source and preview geometry stay distinct

The viewer SHALL label the source export's recorded triangle count separately from the loaded preview's triangle count. It SHALL report whether the loaded preview has vertex-normal attributes. It SHALL state when a detail is unavailable instead of inferring it from another representation.

#### Scenario: Decimated preview has fewer triangles
- **GIVEN** a source export with 1,280 triangles and a preview with 320
- **WHEN** the viewer displays inspection details
- **THEN** it SHALL show 1,280 as source triangles and 320 as preview triangles

#### Scenario: Preview has no vertex normals
- **GIVEN** a loaded preview whose primitives have no vertex-normal attributes
- **WHEN** the viewer displays inspection details
- **THEN** it SHALL say that preview vertex normals are absent

### Requirement: Texture and normal-map details reflect the source export

For a readable validated source export, the viewer SHALL report each inspectable texture's material, channel, and pixel dimensions. It SHALL distinguish a normal-map texture from mesh vertex normals. If texture dimensions cannot be read, it SHALL say so for that texture. It SHALL NOT fetch or display source texture bytes in the browser.

#### Scenario: Embedded normal map has known dimensions
- **GIVEN** a validated source export with an embedded 1024 by 1024 normal map
- **WHEN** the viewer displays inspection details
- **THEN** it SHALL identify the normal channel and show 1024 × 1024 pixels

#### Scenario: Texture reference cannot be inspected
- **GIVEN** a source export referring to an image whose dimensions are unavailable
- **WHEN** the viewer displays inspection details
- **THEN** it SHALL identify the texture channel and state that its dimensions are unavailable

#### Scenario: Source export cannot be read
- **GIVEN** a recorded preview whose source export cannot currently be inspected
- **WHEN** the viewer opens
- **THEN** the preview and annotations SHALL remain available
- **AND** source texture details SHALL be stated as unavailable
