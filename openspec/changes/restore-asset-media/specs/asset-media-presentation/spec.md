# Spec Delta

## Purpose

This capability makes an asset's recorded concept images and validated mesh preview visible in the browser while keeping the repository as the source of media and preserving annotation placement.

## ADDED Requirements

### Requirement: Current concept images are visible on the model sheet

The model sheet SHALL display the current image for each existing concept view through an authenticated read. It SHALL present one card per physical view even when a declared path and a discovered slot name refer to the same image. It SHALL preserve the visibility and selection of annotations anchored under either name, and new pins SHALL use the canonical slot name.

#### Scenario: Declared path and discovered slot refer to one image
- **GIVEN** an asset declares `concept/front.png` and the repository also discovers slot `front`
- **WHEN** the model sheet opens
- **THEN** one card SHALL display the current front image
- **AND** pins recorded under either view name SHALL remain visible and selectable
- **AND** a new pin SHALL name `front`

#### Scenario: No image exists for a declared view
- **GIVEN** an asset declares a view whose image is absent from the repository
- **WHEN** the model sheet opens
- **THEN** the view SHALL remain listed with a specific image-unavailable explanation
- **AND** the remainder of the sheet SHALL remain usable

### Requirement: Reference images do not burden unrelated surfaces

The browser SHALL fetch concept image bytes only when the model sheet is opened. Image bytes SHALL NOT be embedded into server-rendered page data, and a failed image read SHALL NOT fail the asset page.

#### Scenario: Overview and viewer avoid image downloads
- **GIVEN** an asset has concept images
- **WHEN** its Overview or 3D viewer opens
- **THEN** no concept image bytes SHALL be requested

#### Scenario: One image read fails
- **GIVEN** two concept views and one image read fails
- **WHEN** the model sheet opens
- **THEN** the readable image SHALL be displayed
- **AND** the failed view SHALL explain its own failure

### Requirement: Validated previews render in the 3D viewer

The viewer SHALL render the validated preview even when its geometry uses Draco compression, with the decoder supplied by the web deployment. It SHALL continue to request only preview bytes, never the working export. If decoding fails, the viewer SHALL state that the preview could not be decoded and offer a retry while keeping the asset's other information usable.

#### Scenario: Compressed preview opens
- **GIVEN** an asset has a Draco-compressed validated GLB preview
- **WHEN** its 3D viewer opens in a capable browser
- **THEN** the preview mesh SHALL render and its parts SHALL be inspectable

#### Scenario: Decoder failure is actionable
- **GIVEN** the preview bytes arrive but cannot be decoded
- **WHEN** the 3D viewer opens
- **THEN** the viewer SHALL identify preview decoding as the failure
- **AND** it SHALL offer a retry without hiding the asset's annotations
