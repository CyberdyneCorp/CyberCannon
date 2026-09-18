# Spec Delta

## Purpose

Displays an asset's decimated preview mesh in a browser with navigation, framing,
part selection and honest provenance, so a reviewer can inspect form and scale
from any angle without the working export ever leaving the repository.

## ADDED Requirements

### Requirement: The viewer displays the preview, never the working export

The viewer SHALL load the decimated preview mesh produced by the validation run.
It SHALL NOT load, stream, request or otherwise obtain the working export, and no
address reachable by the viewer SHALL resolve to a working export file.

#### Scenario: Preview is what is loaded
- **GIVEN** an asset with a working export and a preview derived from it
- **WHEN** the asset is opened in the viewer
- **THEN** the mesh loaded SHALL be the preview
- **AND** the working export SHALL NOT be requested

#### Scenario: No route exposes the working export
- **WHEN** the addresses the viewer is able to request are enumerated
- **THEN** none of them SHALL resolve to a working export file

### Requirement: The viewer states which export and which revision it is showing

While a preview is displayed, the viewer SHALL identify the export the preview was
derived from and the revision of the specification it is being viewed against.
When the displayed preview was derived from an export that is not the latest
validated export for the asset, the viewer SHALL say so.

#### Scenario: Provenance is visible
- **GIVEN** a preview derived from a named export
- **WHEN** the asset is displayed
- **THEN** the viewer SHALL show the export it was derived from and the
  specification revision in view

#### Scenario: Superseded preview is flagged
- **GIVEN** a preview derived from an export that has since been superseded by a
  newer validated export
- **WHEN** the asset is displayed
- **THEN** the viewer SHALL state that the preview is not derived from the latest
  validated export

### Requirement: Counts are reported against the source export, and preview counts are labelled as such

The viewer SHALL display the triangle count, the object count and the material
count recorded for the **source export** by its validation run. Where the
preview's own counts are shown, they SHALL be labelled as the preview's and SHALL
NOT be presented as the asset's figures. A count that was never recorded SHALL be
shown as unavailable rather than substituted by the preview's.

#### Scenario: Budget-relevant count is the source's
- **GIVEN** a source export of 14310 triangles whose preview contains 4200
- **WHEN** the asset is displayed
- **THEN** the asset's triangle count SHALL be shown as 14310
- **AND** any display of 4200 SHALL be labelled as the preview's count

#### Scenario: Unrecorded count is absent, not inferred
- **GIVEN** an asset whose source material count was never recorded
- **WHEN** the asset is displayed
- **THEN** the material count SHALL be shown as unavailable

### Requirement: Navigation and framing

The viewer SHALL support orbiting around, panning and zooming the displayed mesh
using pointer input, and SHALL provide an action that frames the whole asset. When
a part is selected, framing SHALL be available for that part alone. Navigation
SHALL NOT alter the mesh, the preview, or any stored annotation.

#### Scenario: Frame restores a known view
- **GIVEN** a mesh that has been orbited and zoomed to an arbitrary view
- **WHEN** the frame action is invoked
- **THEN** the whole asset SHALL be visible within the viewport

#### Scenario: Framing a part
- **GIVEN** a selected part
- **WHEN** framing that part is invoked
- **THEN** the view SHALL be positioned so that part fills the viewport
- **AND** the rest of the asset SHALL remain loaded

### Requirement: Part selection and isolation

The viewer SHALL allow a part of the loaded mesh to be selected by pointing at it
and SHALL report the selected part's name. It SHALL allow the selection to be
isolated, hiding all other parts, and to be restored. The viewer SHALL also list
the mesh's parts by name and allow selection from that list. Selection and
isolation are view state and SHALL NOT be written to the specification.

#### Scenario: Selecting names the part
- **GIVEN** a loaded mesh containing a part named `SM_MechScout_Shoulder_L`
- **WHEN** that part is pointed at and selected
- **THEN** the viewer SHALL report the selected part as `SM_MechScout_Shoulder_L`

#### Scenario: Isolation is reversible
- **GIVEN** an isolated part
- **WHEN** isolation is cleared
- **THEN** every part of the mesh SHALL be visible again

#### Scenario: Isolation leaves no trace in the specification
- **GIVEN** a part has been selected and isolated
- **WHEN** the specification file is inspected
- **THEN** it SHALL be unchanged

### Requirement: An asset with no preview says so and says why

When an asset has no preview, the viewer SHALL state that no preview exists,
SHALL state the reason it is able to determine — no export recorded, no successful
validation run, or preview emission failed — and SHALL NOT present an empty
viewport as a loaded asset. The asset's specification, annotations and other
surfaces SHALL remain usable.

#### Scenario: No export yet
- **GIVEN** an asset whose status is `concept` with no export recorded
- **WHEN** the asset is opened in the viewer
- **THEN** the viewer SHALL state that no preview exists because no export has
  been validated
- **AND** the asset's specification SHALL remain readable

#### Scenario: Preview emission failed
- **GIVEN** an export that validated successfully but whose preview emission failed
- **WHEN** the asset is opened in the viewer
- **THEN** the viewer SHALL state that no preview is available and that emission
  failed
- **AND** it SHALL NOT report the export as unvalidated

### Requirement: An unloadable preview is reported, not left blank

When a preview exists but cannot be retrieved or cannot be parsed as a displayable
mesh, the viewer SHALL report that condition, naming the preview it attempted, and
SHALL offer a retry. It SHALL NOT display a blank viewport, and SHALL NOT report
the asset as having no preview.

#### Scenario: Retrieval fails
- **GIVEN** a recorded preview that cannot be retrieved
- **WHEN** the asset is opened in the viewer
- **THEN** the viewer SHALL report that the preview could not be loaded
- **AND** a retry SHALL be offered

### Requirement: Defined degradation when the device cannot render

When the browser or device cannot present the preview — no hardware-accelerated
rendering available, or the rendering context is lost and cannot be restored — the
viewer SHALL fall back to a non-rendering presentation of the asset that shows its
available still imagery, its specification, and its full annotation list including
orphans. In that state, existing annotations SHALL remain readable and triageable,
creating a new 3D anchor SHALL be unavailable and SHALL be stated as unavailable
rather than failing on use, and the page SHALL NOT present an error as the asset's
only content.

#### Scenario: No rendering support
- **GIVEN** a device with no hardware-accelerated rendering available
- **WHEN** the asset is opened in the viewer
- **THEN** the still imagery, specification and annotation list SHALL be presented
- **AND** the viewer SHALL state that 3D display is unavailable on this device
- **AND** the action to place a new 3D anchor SHALL be shown as unavailable

#### Scenario: Rendering context lost mid-session
- **GIVEN** a displayed mesh whose rendering context is lost
- **WHEN** the context cannot be restored
- **THEN** the viewer SHALL move to the non-rendering presentation
- **AND** annotations already open SHALL remain readable

### Requirement: The viewer reuses the shared annotation presentation

Threads, filtering, triage state and the promote/resolve exits presented in the 3D
viewer SHALL be the same behaviour as presented in the 2D model sheet, with no
separate implementation. The viewer's own responsibility SHALL be limited to
producing a 3D anchor from user input and presenting a resolved anchor.

#### Scenario: Same annotation state in both surfaces
- **GIVEN** an annotation filtered out by an active filter in the 2D surface
- **WHEN** the same asset is opened in the 3D viewer with the same filter active
- **THEN** that annotation SHALL be filtered out there as well

#### Scenario: Triage performed in 3D behaves identically
- **GIVEN** an open annotation displayed in the 3D viewer
- **WHEN** it is resolved from the viewer
- **THEN** it SHALL take the same exit, with the same effect on the compiled
  specification, as resolving it from the 2D surface
