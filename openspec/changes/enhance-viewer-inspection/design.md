# Design

## Context

`OrbitControls` updates the camera but no change listener redraws the canvas. The viewer already receives source counts from `PreviewDescriptor` and preview geometry from `LoadedPreview`. `gltf_preview` deliberately strips images and texture references, so texture facts must come from the validated source read already performed by `MeshInspector`.

## Goals / Non-Goals

**Goals:** Immediate camera feedback, accessible zoom actions, source texture dimensions and normal-map channel, and preview vertex-normal coverage with explicit provenance.

**Non-Goals:** Source image delivery, material editing, or changing preview size and validation rules.

## Decisions

1. The scene listens for camera-control changes and renders on demand. The listener is removed with the scene. The scene contract gains `zoomIn` and `zoomOut`; controls and framing remain scene-owned. The component adds gesture help and buttons, while its existing tap-versus-drag rule continues to protect annotation placement.
2. `LoadedPreview`/`LoadedSummary` report the number of mesh primitives and how many carry a `normal` vertex attribute. The browser derives a human-readable status from those counts. These describe the **preview** and never stand in for source normals.
3. The `MeshInspector` port's `InspectedMesh` gains an optional `SourceVisuals` value object containing source texture references. The glTF adapter reads material channel mappings and image dimensions from embedded GLB image buffer views or data URIs with Pillow. External or unreadable images retain the channel with unknown dimensions. FBX and OBJ source texture inspection is explicitly unavailable. This is an observation, not a validation rule: adapters extract it, the application carries it, and no domain budget logic depends on it.
4. `get_preview_descriptor` reuses its source inspection result for counts, names, and visuals, and degrades visuals independently when inspection fails. The HTTP payload carries only channel, material, dimensions and availability; no image bytes or working-export URL. The viewer shows source texture details in a compact list under the existing counts.

## Risks / Trade-offs

- Reading image headers adds bounded work to the source inspection already on the descriptor path. Pillow opens headers without decoding full pixel arrays; malformed images become unknown dimensions rather than breaking the viewer.
- External texture paths may leave the worktree or require fetching. This change does not follow them, so the UI reports their dimensions as unavailable.
- The preview can have generated normals even if the source did not. Its status is labelled as preview geometry to avoid presenting it as a source fact.
