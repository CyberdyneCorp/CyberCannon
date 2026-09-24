# Proposal

## Why

The hosted viewer loads a 3D preview, but orbit and zoom do not redraw the canvas as the camera moves. Its figures also stop at triangle, object, and material counts, leaving artists unable to inspect texture resolution or normal data while reviewing an export.

## What Changes

- Redraw the scene during orbit, pan, and zoom, and explain mouse, touch, and keyboard controls beside the viewport.
- Add explicit zoom controls and a reset view action for users without a wheel or trackpad.
- Show source export triangles alongside the preview triangle count, with their distinct provenance retained.
- Report source texture dimensions and normal-map usage, and identify whether preview geometry carries vertex normals. State when a format or image cannot provide a detail.

## Capabilities

### New Capabilities

- `viewer-inspection`: Interactive camera navigation and honest technical inspection of a validated source and its lightweight preview.

### Modified Capabilities

None. The original viewer behavior lives in unsynced `add-viewer-3d` change specs; this delta adds inspection details without changing their requirements.

## Impact

The browser scene and viewer UI, the mesh inspector's read result, the preview descriptor payload, and their tests. No source-export bytes are sent to the browser. The existing preview continues to drop textures to keep it small.

## Non-goals

- Editing a mesh, its materials, or source textures.
- Showing source texture pixels or changing the validation verdict.
- Replacing the decimated preview with the full working export.

## Roadmap position

This is a post-M3 viewer usability improvement after reference images and Draco previews became visible in production. It supports artist review before broader project-registry work.
