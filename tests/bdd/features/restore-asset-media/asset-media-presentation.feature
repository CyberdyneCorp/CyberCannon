# Generated from openspec/changes/restore-asset-media/specs/asset-media-presentation/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:restore-asset-media @capability:asset-media-presentation @spec:openspec/changes/restore-asset-media/specs/asset-media-presentation/spec.md
Feature: asset-media-presentation

  Rule: Current concept images are visible on the model sheet

    Scenario: Declared path and discovered slot refer to one image
      Given an asset declares `concept/front.png` and the repository also discovers slot `front`
      When the model sheet opens
      Then one card SHALL display the current front image
      And pins recorded under either view name SHALL remain visible and selectable
      And a new pin SHALL name `front`

    Scenario: No image exists for a declared view
      Given an asset declares a view whose image is absent from the repository
      When the model sheet opens
      Then the view SHALL remain listed with a specific image-unavailable explanation
      And the remainder of the sheet SHALL remain usable

  Rule: Reference images do not burden unrelated surfaces

    Scenario: Overview and viewer avoid image downloads
      Given an asset has concept images
      When its Overview or 3D viewer opens
      Then no concept image bytes SHALL be requested

    Scenario: One image read fails
      Given two concept views and one image read fails
      When the model sheet opens
      Then the readable image SHALL be displayed
      And the failed view SHALL explain its own failure

  Rule: Validated previews render in the 3D viewer

    Scenario: Compressed preview opens
      Given an asset has a Draco-compressed validated GLB preview
      When its 3D viewer opens in a capable browser
      Then the preview mesh SHALL render and its parts SHALL be inspectable

    Scenario: Decoder failure is actionable
      Given the preview bytes arrive but cannot be decoded
      When the 3D viewer opens
      Then the viewer SHALL identify preview decoding as the failure
      And it SHALL offer a retry without hiding the asset's annotations
