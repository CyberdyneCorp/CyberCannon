# Proposal

## Why

Two-dimensional feedback stops being enough the moment the asset is a mesh. "The
shoulder pauldron reads wrong from behind" is unanswerable on a model sheet: the
reviewer cannot get behind the model, and the modeller cannot tell which shoulder,
at which angle, at which frame of the walk cycle. The feedback that matters most
in a 3D pipeline — silhouette from a gameplay camera, a socket pointing the wrong
way, a limb clipping mid-animation — is exactly the feedback a 2D surface cannot
carry.

This is **roadmap position 5**, and it comes now for two reasons. First, it is the
cheapest surface in the project: `add-model-sheet-2d` already built the
`AnnotationViewModel`, threads, triage and the promote/resolve exits, and this
change reuses all of it unchanged. The 3D view's entire job is to turn a click
into an `Anchor3D` and an `Anchor3D` back into a camera and a highlight —
`project.md`'s selective-MVVM bet says that is what makes "support 2D and 3D" cost
far less than twice, and this change is where the bet is settled. Second, the
preview mesh it displays has existed since change 1: `asset-preview` emits a
decimated, compressed GLB as a by-product of every validation run, precisely so
that no browser ever sees a 200 MB working export.

The hard part is not the viewer, it is **anchoring**, and `project.md` already
decided how: the durable key is the named part, the point and normal are
positioning hints, the saved camera restores the angle, and a renamed or deleted
part yields an **orphan** rather than a silently relocated pin. This change turns
that decision into resolution behaviour — re-projection, orphan reporting, and
re-anchoring by hand — because the day a mesh is retopologised is the day all the
feedback on it either survives or quietly becomes a lie.

## What Changes

- **A browser 3D viewer over the decimated preview** — orbit, pan, zoom, framing,
  part selection and isolation. The working export is never served to a browser,
  and there is no route by which it could be.
- **Provenance on screen** — which export and which revision is being displayed,
  and whether that preview is derived from the latest validated export or an older
  one. A reviewer annotating a stale preview is a reviewer wasting a modeller's day.
- **Counts that mean something** — triangle, object and material counts shown as
  the **source export's** validated figures, with the preview's own decimated
  count labelled separately, so nobody argues about a budget using a number the
  budget was never measured against.
- **Anchor resolution against a loaded mesh** — the named part is looked up, the
  stored point is re-projected onto the nearest surface **of that part**, and the
  saved camera is restored when the annotation is opened. Point, normal and camera
  are hints; the part is identity.
- **Orphans are explicit and actionable** — a missing or renamed part produces a
  visibly orphaned annotation, listed as such, never relocated. An orphan can be
  re-anchored to a part by hand, attributed to the person doing it.
- **Animation playback from the preview's clips** — listing, play/pause, scrub,
  loop, playback speed, and a mapping from each clip to the design state it
  satisfies. A declared state with **no** clip is shown as explicitly absent, not
  silently missing.
- **Annotating a paused frame** — the clip and a normalized time are recorded
  alongside the camera as viewing hints, and replaying the annotation restores
  clip, time and camera. The anchor's hint geometry is recorded in the part's own
  space, so a pose never corrupts it.
- **A defined degradation** — a device that cannot render the preview shows the
  asset's still imagery and the full annotation list, read and triage still work,
  and 3D anchor creation is disabled rather than broken.

## Capabilities

### New Capabilities

- `viewer-3d`: loading and displaying an asset's preview mesh in a browser —
  navigation, framing, counts, export and revision provenance, part selection and
  isolation, the no-preview state, and degradation on a device that cannot render.
- `anchor-resolution`: resolving a stored 3D anchor against a loaded mesh — the
  named part as durable key, re-projection of positioning hints, camera
  restoration, orphan reporting, and manual re-anchoring.
- `animation-playback`: playing the clips carried by a preview — transport,
  speed, loop, clip-to-design-state coverage including states with no clip, and
  annotating a paused frame.

### Modified Capabilities

None — no earlier change is archived yet, so a delta against an unarchived
capability cannot be written. Requirements that touch preview contents, annotation
authoring or the HTTP surface are stated inside this change's own capabilities as
behaviour this viewer requires.

## Non-goals

Explicitly **not** in this change:

- **No annotation model, threads, filtering or triage.** `annotation-authoring`
  and `annotation-triage` (`add-model-sheet-2d`) own those, and the
  `AnnotationViewModel` is reused as-is. If this change needs to change it, the
  selective-MVVM decision was wrong and that is worth knowing loudly.
- **No promotion path of its own.** Promotion to a durable rule remains the art
  director's action in the triage surface, and remains not agent-callable.
- **No mesh editing, no sculpting, no paint-over.** No brushes, no layers, no
  vertex manipulation, no transform gizmo. The viewer never writes geometry.
- **No serving of the working export.** No streaming LOD chain, no progressive
  load of the source FBX/GLB, no in-browser decimation. The preview is produced by
  the validator run and nowhere else.
- **No change to the anchor format.** `Anchor3D` was defined in `asset-spec`; this
  change resolves it, it does not redefine it, and it still SHALL NOT carry
  triangle indices or barycentric coordinates.
- **No engine-accurate rendering.** No PBR parity with Unreal or Unity, no
  lightmaps, no post-processing stack, no material graph preview. The viewer shows
  form, scale and motion, not final pixels.
- **No authoring of animation.** No retiming, no blending, no state-machine
  editing. Clips are played, never produced.
- **No HTTP endpoints, auth or blob delivery of its own.** `http-api`,
  `auth-integration` and `blob-storage` (`add-web-backend`) supply those.
- **No MCP exposure.** Nothing here becomes an agent tool; `add-mcp-writes` owns
  the write surface and promotion stays outside it.
- **No AI mesh correction, no variation voting** — deferred by `project.md`.

## Impact

- **New frontend code** — `apps/cybercanon/web/` gains a viewer route, a
  `Viewer3D.svelte` view, a thin three.js scene module (loading, camera,
  raycasting, isolation, clip transport) and an animation transport component.
  The shared `AnnotationViewModel` (`*.svelte.ts`) gains **no** 3D-specific
  logic — the view produces `Anchor3D` and consumes a resolution result.
- **New backend code** — a domain `AnchorResolution` value object and a pure
  orphan-detection function over the part names in `MeshFacts`, so the annotation
  list can mark orphans without a GPU; a use case returning an asset's preview
  descriptor (export, revision, source counts, clip list, part list) for the
  viewer to load.
- **New dependency** — `three` in the web app only, pinned. No new backend
  dependency: clip and part names come from the existing `MeshInspector` boundary.
- **Preview contents** — the preview emitted during validation must retain part
  names (already required) **and** the source's animation clips. Where it does
  not, the viewer reports clips unavailable for that preview rather than claiming
  the asset has none.
- **Consumer-side impact** — none on `asset.yaml`'s schema. An existing annotation
  authored in 2D is unaffected; a 3D annotation authored here is an ordinary
  annotation entry that the compiler and the MCP read surface already understand.
