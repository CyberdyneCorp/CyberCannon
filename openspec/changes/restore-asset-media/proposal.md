# Proposal

## Why

The hosted model sheet lists reference views without pixels, and the 3D viewer cannot decode the compressed preview emitted by validation. These are the main visual surfaces for reviewing an asset, so their failure blocks the artist workflow even though the metadata and annotations load.

## What Changes

- Load each current concept image through the existing authenticated view-revision API and show it on the sheet with its annotations.
- Present one card for a reference that appears both as a declared path and as a discovered slot, while preserving pins anchored under either name.
- Decode Draco-compressed GLB previews in the browser using decoder assets shipped with the web app.
- Give a specific, retryable message when an image or preview cannot be presented.

## Capabilities

### New Capabilities

- `asset-media-presentation`: Complete the browser presentation of concept views and validated 3D previews specified by the existing model-sheet and viewer changes, which have not yet been synced to main specs.

### Modified Capabilities

None.

## Impact

The SvelteKit asset route, typed API client and cache, model sheet, 3D scene loader, static web assets, and frontend tests. The existing HTTP API, git content, domain objects, and database schema remain unchanged.

## Non-goals

- Serve working exports to browsers or edit reference images in the sheet.
- Change image ingestion, validation, annotation permissions, or content repository files.
- Add a new media storage service or CDN dependency.

## Roadmap position

This is a post-M3 hosted usability repair after persistent navigation. It comes before wider project-registry work because reviewers need to see the reference and preview media already recorded for an asset.
