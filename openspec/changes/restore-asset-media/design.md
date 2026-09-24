# Design

## Context

See `proposal.md`. The model sheet currently receives an empty image-source map. The HTTP surface already exposes a repository-backed view history and a base64 image read for a selected revision, independent of MinIO. The preview emitter declares `KHR_draco_mesh_compression`, while both `GLTFLoader` instances in the web scene have no `DRACOLoader`.

## Goals / Non-Goals

**Goals:** Display current concept pixels once per physical view; decode the existing preview format; keep media failures local to their card or viewer.

**Non-Goals:** New API routes, image mutations, working-export downloads, or changes to repository metadata.

## Decisions

1. The typed `CanonClient` reads current view history and its current revision image with the session bearer. `CanonApi` caches these under a slot-scoped key. The asset route resolves images only on the browser's sheet load, maps them to data URLs using the current file's extension, and passes results into the presentation. This reuses the repository-backed `RepositoryHost` and `SpecStore` ports through the existing HTTP adapter; no domain value object or backend port changes.
2. A pure sheet mapping turns a declared `concept/<slot>.<ext>` alias and the discovered `<slot>` into one visual card. The card keeps both names as annotation aliases and uses the slot for new anchors. The annotation domain value `Anchor2D` stays unchanged, and the alias rule remains a frontend presentation concern.
3. Both GLTF parses use one configured loader factory with a `DRACOLoader` pointing at decoder assets shipped under the web app's static directory. The existing `MeshInspector` and `DerivedPreview` domain/application boundary remains untouched. The decoder belongs to the web adapter; it does not decide mesh validity.
4. The view reports media read and decode errors explicitly. A failed image never changes route state; a failed preview leaves the existing retry path and annotations available.

## Risks / Trade-offs

- Base64 data URLs increase browser memory for displayed images. Fetch only on the sheet and cache per slot; revisit a streamed image endpoint if real assets become too large.
- Decoder files must match the pinned `three` version. Copy them from that version and verify the built web image serves them.
- Historical path anchors remain readable even after cards are grouped; regression tests cover both aliases.

## Migration Plan

Ship the web image only. Existing API routes and stored media need no migration. Rollback is the previous web image; no durable data is changed.
