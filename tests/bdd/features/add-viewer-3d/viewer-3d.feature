# Generated from openspec/changes/add-viewer-3d/specs/viewer-3d/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-viewer-3d @capability:viewer-3d @spec:openspec/changes/add-viewer-3d/specs/viewer-3d/spec.md
Feature: viewer-3d

  Rule: The viewer displays the preview, never the working export

    Scenario: Preview is what is loaded
      Given an asset with a working export and a preview derived from it
      When the asset is opened in the viewer
      Then the mesh loaded SHALL be the preview
      And the working export SHALL NOT be requested

    Scenario: No route exposes the working export
      When the addresses the viewer is able to request are enumerated
      Then none of them SHALL resolve to a working export file

  Rule: The viewer states which export and which revision it is showing

    Scenario: Provenance is visible
      Given a preview derived from a named export
      When the asset is displayed
      Then the viewer SHALL show the export it was derived from and the specification revision in view

    Scenario: Superseded preview is flagged
      Given a preview derived from an export that has since been superseded by a newer validated export
      When the asset is displayed
      Then the viewer SHALL state that the preview is not derived from the latest validated export

  Rule: Counts are reported against the source export, and preview counts are labelled as such

    Scenario: Budget-relevant count is the source's
      Given a source export of 14310 triangles whose preview contains 4200
      When the asset is displayed
      Then the asset's triangle count SHALL be shown as 14310
      And any display of 4200 SHALL be labelled as the preview's count

    Scenario: Unrecorded count is absent, not inferred
      Given an asset whose source material count was never recorded
      When the asset is displayed
      Then the material count SHALL be shown as unavailable

  Rule: Navigation and framing

    Scenario: Frame restores a known view
      Given a mesh that has been orbited and zoomed to an arbitrary view
      When the frame action is invoked
      Then the whole asset SHALL be visible within the viewport

    Scenario: Framing a part
      Given a selected part
      When framing that part is invoked
      Then the view SHALL be positioned so that part fills the viewport
      And the rest of the asset SHALL remain loaded

  Rule: Part selection and isolation

    Scenario: Selecting names the part
      Given a loaded mesh containing a part named `SM_MechScout_Shoulder_L`
      When that part is pointed at and selected
      Then the viewer SHALL report the selected part as `SM_MechScout_Shoulder_L`

    Scenario: Isolation is reversible
      Given an isolated part
      When isolation is cleared
      Then every part of the mesh SHALL be visible again

    Scenario: Isolation leaves no trace in the specification
      Given a part has been selected and isolated
      When the specification file is inspected
      Then it SHALL be unchanged

  Rule: An asset with no preview says so and says why

    Scenario: No export yet
      Given an asset whose status is `concept` with no export recorded
      When the asset is opened in the viewer
      Then the viewer SHALL state that no preview exists because no export has been validated
      And the asset's specification SHALL remain readable

    Scenario: Preview emission failed
      Given an export that validated successfully but whose preview emission failed
      When the asset is opened in the viewer
      Then the viewer SHALL state that no preview is available and that emission failed
      And it SHALL NOT report the export as unvalidated

  Rule: An unloadable preview is reported, not left blank

    Scenario: Retrieval fails
      Given a recorded preview that cannot be retrieved
      When the asset is opened in the viewer
      Then the viewer SHALL report that the preview could not be loaded
      And a retry SHALL be offered

  Rule: Defined degradation when the device cannot render

    Scenario: No rendering support
      Given a device with no hardware-accelerated rendering available
      When the asset is opened in the viewer
      Then the still imagery, specification and annotation list SHALL be presented
      And the viewer SHALL state that 3D display is unavailable on this device
      And the action to place a new 3D anchor SHALL be shown as unavailable

    Scenario: Rendering context lost mid-session
      Given a displayed mesh whose rendering context is lost
      When the context cannot be restored
      Then the viewer SHALL move to the non-rendering presentation
      And annotations already open SHALL remain readable

  Rule: The viewer reuses the shared annotation presentation

    Scenario: Same annotation state in both surfaces
      Given an annotation filtered out by an active filter in the 2D surface
      When the same asset is opened in the 3D viewer with the same filter active
      Then that annotation SHALL be filtered out there as well

    Scenario: Triage performed in 3D behaves identically
      Given an open annotation displayed in the 3D viewer
      When it is resolved from the viewer
      Then it SHALL take the same exit, with the same effect on the compiled specification, as resolving it from the 2D surface
