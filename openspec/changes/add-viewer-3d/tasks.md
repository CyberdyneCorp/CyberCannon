# Tasks

## 1. Domain — anchor resolution policy without geometry

- [ ] 1.1 Model `AnchorResolution` as a frozen value object with outcome `resolved | partial | orphaned`, the expected part, the expected bone and the reason; verify `lint-imports` still reports zero third-party imports in the domain
- [ ] 1.2 Implement orphan and partial detection as a pure function over an anchor and the part and bone names recorded in `MeshFacts` (D6); verify part-present, part-renamed, part-absent, bone-absent and bone-present cases from hand-built facts with no mesh files on disk
- [ ] 1.3 Implement the rule that nothing resolves an orphan automatically — a pure function that never substitutes a different part — and verify a test where a near-identical part name is present still yields `orphaned`
- [ ] 1.4 Add the playback hint fields (`clip`, normalized `t` in 0.0–1.0) to `Anchor3D` as optional viewing hints (D9), and verify tests assert `t` outside the range is rejected and that no frame-index field exists on the type
- [ ] 1.5 Verify the topology prohibition structurally: a test asserts `Anchor3D` has no triangle-index, barycentric or vertex-index field and that its constructor rejects unknown fields

## 2. Application — what the viewer needs to load an asset

- [ ] 2.1 Implement a `get_preview_descriptor` use case returning the preview reference, the source export, the specification revision, whether the source export is the latest validated one, the source export's triangle/object/material counts, the part names and the clip names; verify absent figures are returned as unavailable rather than zero
- [ ] 2.2 Implement the state-to-clip coverage projection consuming the required clip name already derived by the specification (D8) — each declared state with its clip present or absent, plus clips satisfying no state; verify a two-state asset with one clip reports one satisfied state, one state without a clip and zero unclaimed clips
- [ ] 2.3 Implement an `annotation_resolutions` use case returning each annotation's `AnchorResolution` against a given export; verify it runs with no mesh loaded and that the orphan count matches the domain function
- [ ] 2.4 Implement the re-anchor use case taking a new part, hint point, normal and camera, requiring an `Attribution` with a non-optional actor; verify the annotation keeps its identifier, text, replies and open state and that the recorded change names both person and automated caller
- [ ] 2.5 Verify the re-anchor use case refuses an automated caller acting on its own, and that no promotion path exists through it
- [ ] 2.6 Verify the no-preview reasons are distinguishable at the use-case level — no export recorded, no successful validation, preview emission failed — with a test per case asserting the reported reason

## 3. HTTP surface for the viewer

- [ ] 3.1 Expose the preview descriptor and annotation resolutions through the existing `http-api` routing conventions, and verify a request for an asset with no preview returns the descriptor with its reason rather than an error status
- [ ] 3.2 Expose the re-anchor action through the existing write conventions with identity taken from the credential; verify a request carrying an actor parameter does not change the attributed actor
- [ ] 3.3 Add the D7 enforcement test: enumerate every address the web surface can produce for an asset and assert none resolves to a working export path
- [ ] 3.4 Verify preview delivery is byte-identical to the stored preview blob and that a missing blob is reported as unretrievable, naming the preview

## 4. Scene module — loading, navigation, picking

- [ ] 4.1 Add the pinned `three` dependency to the web app only and verify the backend dependency set is unchanged
- [ ] 4.2 Implement the scene module interface (D1) — `load`, `pick`, `resolve`, `applyCamera`, `playClip` — and verify a headless test loads a fixture GLB and reports its part names
- [ ] 4.3 Implement orbit, pan, zoom, frame-all and frame-selected; verify frame-all leaves the whole bounding box within the frustum and frame-selected leaves the selected part's bounding box within it
- [ ] 4.4 Implement picking that returns only the picked object's name and the hit point in that object's local space (D3); verify a test asserts the returned value carries no face index or barycentric weights, and that a pick on empty space returns nothing
- [ ] 4.5 Implement part selection, isolation and restore over the fixture mesh, and verify a pick against an isolated-away part records nothing
- [ ] 4.6 Verify no persistence of view state (D12): a test exercising selection, isolation, loop and speed asserts the specification file is byte-identical afterwards

## 5. Scene module — resolution and re-projection

- [ ] 5.1 Implement the per-part lazy BVH and nearest-point-on-surface query restricted to the named part (D4); verify a hint nearer to another part's surface still resolves onto the named part
- [ ] 5.2 Verify camera independence: resolving the same anchor from two different viewing directions yields an identical surface position
- [ ] 5.3 Implement rest-pose hint recording by inverting the current node and skinning transform at pick time (D10); verify the same surface location annotated at rest and mid-clip produces equivalent recorded point and normal
- [ ] 5.4 Implement the displacement measure normalized by the part's bounding-box diagonal and the configured threshold (D5); verify an above-threshold case reports possibly displaced with a distance and a below-threshold case does not
- [ ] 5.5 Verify retopology survival end to end with two fixture exports of the same asset — different triangle layout, same part names — asserting every anchor still resolves to its part
- [ ] 5.6 Verify preview-versus-source equivalence: the same anchor resolved against a fixture export and its emitted preview yields the same named part, and a part dropped by preview emission is reported as a preview limitation rather than as removed from the asset

## 6. Viewer view — annotations over the shared ViewModel

- [ ] 6.1 Build `Viewer3D.svelte` consuming the shared `AnnotationViewModel` from `add-model-sheet-2d` unchanged (D2); verify the diff of this change touches no ViewModel file
- [ ] 6.2 Add the D2 structural test asserting the viewer components import no thread, filter or triage module directly and reach them only through the ViewModel
- [ ] 6.3 Implement anchor placement producing an `Anchor3D` with part, rest-pose point and normal, and the current camera; verify placement on empty space creates nothing and states that a part must be pointed at
- [ ] 6.4 Implement camera restoration on opening an annotation and part framing when no camera was recorded; verify the annotation's recorded camera is unchanged after the reader moves the view
- [ ] 6.5 Implement orphan presentation — visibly orphaned, listed, countable — and the partial presentation naming the missing bone; verify counts match the use case's resolutions for the same export
- [ ] 6.6 Implement manual re-anchoring from the viewer by selecting a part, and verify through the interface that the annotation ceases to be orphaned and retains its thread
- [ ] 6.7 Verify cross-surface parity: an annotation filtered out in the 2D surface is filtered out in the viewer under the same filter, and resolving from the viewer produces the same compiled-specification effect as resolving from the 2D surface

## 7. Viewer view — provenance, counts and degradation

- [ ] 7.1 Display the source export and specification revision in view, and verify a preview derived from a superseded export is stated as not derived from the latest validated export
- [ ] 7.2 Display the source export's triangle, object and material counts with any preview count labelled as the preview's; verify a fixture where the two differ shows the source figure as the asset's and never substitutes the preview's for an unavailable count
- [ ] 7.3 Implement the no-preview presentation with its three reasons and the unloadable-preview presentation with a retry; verify each case renders and that the specification remains readable
- [ ] 7.4 Implement the non-rendering degradation (D11) — still imagery, specification, full annotation list with triage, anchor placement shown as unavailable; verify it under a simulated absence of rendering support
- [ ] 7.5 Implement context-loss handling with one restoration attempt restoring camera and paused clip position, falling back to the degraded presentation; verify both outcomes with a simulated context loss

## 8. Animation playback

- [ ] 8.1 Implement clip listing with durations from the loaded preview, and the explicit no-clips statement with no transport offered; verify both from fixtures
- [ ] 8.2 Implement the distinction between an asset with no animation and a preview that lost its clips; verify the case where the export is recorded as carrying a clip the preview does not
- [ ] 8.3 Implement play, pause, resume, scrub, loop and at least three playback speeds with the current position displayed; verify scrubbing to the same position from different starting points yields an identical pose and that displayed duration is unaffected by speed
- [ ] 8.4 Present state coverage from the use case (D8) — satisfied states, declared states with no clip, states declared unanimated, and unclaimed clips; verify a missing clip is listed rather than omitted and an unanimated state is not shown as a gap
- [ ] 8.5 Implement anchor authoring during playback recording clip name and normalized position (D9) alongside the rest-pose hint; verify the recorded value is a proportion, that no frame index is stored, and that removing the clip from a later export does not orphan the annotation
- [ ] 8.6 Implement replay — select the recorded clip, hold it paused at the recorded position, restore the camera — and the degraded path when the clip is absent; verify both, including that the annotation opens against the rest pose and states the clip is unavailable
- [ ] 8.7 Verify playback never rewrites anchors: a test plays a clip through with looping and asserts every annotation's recorded anchor is unchanged

## 9. Acceptance and project hygiene

- [ ] 9.1 Run the retopology acceptance: annotate four parts of an asset, re-export it retopologised with one part renamed, and verify three annotations resolve, one is orphaned naming the missing part, and none moved to another part
- [ ] 9.2 Run the animation acceptance: annotate a paused frame of a walk cycle, reload the asset in a new session, open the annotation and verify clip, position and camera are restored
- [ ] 9.3 Verify the selective-MVVM claim in the change's own diff — the shared ViewModel is unmodified and the 3D-specific code is confined to the view and the scene module; record any leakage as a finding for the design review
- [ ] 9.4 Update `openspec/project.md`'s planned-changes table to mark roadmap position 5 specified, and verify `openspec validate --all --strict` passes
- [ ] 9.5 Run the full test suite, `lint-imports`, and the cognitive complexity check; confirm the frontend target of 8–12 per function holds for the scene module and the viewer components, flagging any genuinely irreducible function rather than splitting it artificially
