# Design

## Context

`add-model-sheet-2d` built the `AnnotationViewModel` — threads, filtering, triage,
the promote/resolve exits — and proved it on a flat image where an anchor is a
`view` plus a normalized coordinate. This change adds the second view over that
same ViewModel, where an anchor is a named part plus hints. `project.md` claims
this is what makes "support 2D and 3D" cost far less than twice; if the ViewModel
needs 3D-specific logic, the claim was wrong and the cheapest place to learn that
is here.

The genuinely hard problem is not the renderer. It is that a mesh is re-exported
constantly, and a pin must survive that. `project.md` already fixed the shape of
the answer — durable key is the named part, point and normal are hints, a missing
part orphans — and `asset-spec` already fixed the stored format. What is left, and
what this change decides, is **how a stored anchor becomes a pixel on a specific
loaded mesh**, and what happens when that mesh has changed underneath it.

Two constraints from `project.md` bound everything below: the working export is
never served to a browser, and an anchor may never be stored by topology.

## Goals / Non-Goals

**Goals:**

- Make a pin survive a retopology, or fail loudly. There is no third acceptable
  outcome.
- Keep `AnnotationViewModel` untouched: the view produces an `Anchor3D`, consumes
  a resolution result, and owns nothing else.
- Make orphan status answerable without a GPU, so the annotation list is honest
  before the viewer has loaded anything.
- Make a 3D review legible to someone who was not in the room: open an annotation,
  get the author's camera, the author's clip, the author's frame.

**Non-Goals (design level):**

- No rendering fidelity work. No PBR parity, no shadows, no post-processing.
- No streaming or LOD chain. One preview, loaded once.
- No collaborative presence, cursors or live sessions.
- No geometry caching across sessions beyond the browser's ordinary HTTP cache.

## Decisions

### D1 — three.js over the preview GLB, wrapped in one scene module

The viewer is a thin module owning a `three.js` scene: loader, camera controls,
raycaster, part registry, clip mixer. Everything else — Svelte components, the
ViewModel — talks to it through a small interface (`load(url)`,
`pick(x, y) -> partName | null`, `resolve(anchor) -> Resolution`,
`applyCamera(camera)`, `playClip(name, t)`).

*Why:* the preview is already GLB (`asset-preview`), and three.js reads it
natively with animation clips and node names intact. **Alternative rejected:** a
packaged web component such as a model viewer element — less code up front, but
it gives no raycast hook into named parts, no clip transport at this granularity,
and no way to keep the pick result out of the ViewModel. **Cost accepted:** a
substantial frontend dependency, a pinned version, and orbit/pan/zoom implemented
against its controls rather than inherited from a higher-level widget.

### D2 — `AnnotationViewModel` is reused unchanged; the view is an anchor codec

The ViewModel's surface stays `Anchor`-shaped. `Viewer3D.svelte` is responsible
for exactly two conversions: pointer input → `Anchor3D{part, bone?, point, normal,
camera, clip?, t?}`, and `Anchor3D` + loaded mesh → a screen position plus a
resolution state. Threads, filters, triage and status are read from the ViewModel
and never reimplemented. A structural test asserts the viewer's components import
no triage or thread module directly.

*Why:* this is the selective-MVVM bet from `project.md`, and it only pays if the
boundary is enforced rather than intended. **Alternative rejected:** a
`Viewer3DViewModel` wrapping the shared one — it reads well for a week and then
holds a second copy of "which annotations are visible". **Cost accepted:** the
shared ViewModel must stay anchor-agnostic, so anything genuinely 3D — the part
registry, the orphan list for the *loaded* mesh — lives in the view and is tested
through the scene module's interface rather than through the ViewModel's tests.

### D3 — The pick result is narrowed to a name at the boundary; topology is discarded there

A raycast returns an intersection carrying the object, the face index, the
barycentric weights and the world point. The scene module returns **only** the
object's name and the point transformed into that object's local space. `Anchor3D`
has no field capable of holding a face index, so the discard is structural rather
than disciplined.

*Why:* `asset-spec` forbids topology-based anchors, and the only reliable way to
enforce a prohibition is to make the forbidden value have nowhere to go. A face
index that exists anywhere in the pipeline eventually gets persisted "just as a
fallback". **Alternative rejected:** storing the face index as a fast path with
the part name as a fallback — the fast path silently wins on a re-export and
places the pin on a different triangle of a different shape.

### D4 — Re-projection is a nearest-point query restricted to the named part, in that part's local space

Resolution builds (lazily, per part, on first use) a bounding-volume hierarchy
over that part's triangles and returns the closest point on its surface to the
hint. Other parts are not candidates, at any distance. The hint is stored and
compared in the part's local space, so a part that was moved, rotated or posed
does not drag its annotations.

*Why:* the alternative most people reach for — casting a ray along the stored
normal — fails exactly when it matters: after a retopology the surface may have
moved off that ray entirely, and the ray then either misses or hits something
behind. Nearest-point always answers, and restricting it to the named part means
the answer is never the wrong part. **Cost accepted:** a BVH build per part on
first resolution, and on a heavily retopologised part the nearest point can be
centimetres from where the author pointed. That cost is deliberate: an
approximately placed pin on the right part is reviewable; a precisely placed pin
on the wrong part is a bug report about the wrong component.

### D5 — Displacement is measured and shown, never absorbed

Resolution returns the distance between the hint and the re-projected point,
normalized by the part's bounding-box diagonal. Above a configured proportion the
annotation renders as *possibly displaced*, with the distance stated.

*Why:* D4's cost is real, and silence about it is what turns "this pin is a bit
off" into "the modeller fixed the wrong area". The threshold is a number in
configuration, so it can be tuned without touching a specification.
**Alternative rejected:** orphaning on large displacement — that throws away a
still-valid part reference because geometry changed, which is precisely the
brittleness the dual anchor exists to avoid.

### D6 — Orphan detection is a domain decision over part names; re-projection is a view concern

"Is this anchor's part present in this export?" is answered in the Python domain
by a pure function over the part names already recorded in `MeshFacts`, yielding
an `AnchorResolution` of `resolved | partial | orphaned`. Only the geometric
placement needs the mesh, and that stays in the browser.

*Why:* an orphan list that requires a GPU is a list nobody sees. With the split,
the asset page, the MCP read surface and the compiled briefing can all say "four
annotations are orphaned on the current export" with no renderer anywhere.
**Alternative rejected:** computing everything client-side after load — simpler
wiring, but then orphan counts exist only where three.js does. **What stays where:**
`Anchor3D`, `AnchorResolution` and the orphan/partial policy are domain; the BVH,
the raycast and the camera are adapter- and view-side and never enter the domain.

### D7 — The viewer addresses previews only, and that is enforced at the API, not the UI

The viewer loads a preview through the blob delivery surface owned by
`add-web-backend`. A test enumerates the addresses the web surface can produce for
an asset and asserts none resolves to a working export path.

*Why:* `project.md`'s whole preview design exists so a browser never pulls a
200 MB export; a rule only held in the frontend is one `fetch` away from being
broken. **Alternative rejected:** relying on the UI never offering the link.

### D8 — The state-to-clip mapping is the one already specified, consumed verbatim

`asset-spec` derives a required clip name for each declared state from the naming
convention, or from the state's explicit `clip`. The viewer asks for that derived
name and matches it exactly against the clips in the preview. It performs no fuzzy
matching, no case-folding beyond the convention's own rules, and no guessing.

*Why:* two places deriving the same mapping is the `design`/`modeling` lens
divergence from `add-mcp-read-server` D2 in a new costume. **Alternative rejected:**
heuristic matching in the viewer so that a nearly-named clip still shows as
satisfying its state — it hides exactly the naming drift the validator exists to
catch. **Cost accepted:** a clip named one character off shows as *no clip for this
state* plus *an unclaimed clip*, which is noisier than a fuzzy match and is the
correct report.

### D9 — Playback position is stored as a proportion of clip duration, not a frame

`Anchor3D`'s optional playback hint is `{clip: name, t: 0.0–1.0}`.

*Why:* frame indices are meaningless across a frame-rate change, and
`asset-validation` already treats frame rate as a fact that can legitimately
differ or be unavailable per format. A proportion survives a re-export at a
different rate and degrades to "about here" rather than to a wrong pose.
**Alternative rejected:** seconds, which survives a rate change but not a clip
that was retimed — the common editing operation. **Cost accepted:** sub-frame
rounding on replay; the restored pose can be one frame off the authored one.

### D10 — The pose at authoring time never touches the stored hint

The point and normal recorded when annotating a paused frame are the *rest-pose*
local coordinates of the picked surface on the picked part, obtained by inverting
the current skinning/node transform at pick time. Playback state is recorded
separately, as D9's hint.

*Why:* if hints were stored in the posed frame, the same physical spot annotated
during a walk cycle and at rest would produce two different anchors, and every
resolution against a differently-posed load would drift. Separating "where on the
part" from "what the model was doing" keeps the durable data pose-invariant.
**Cost accepted:** an inverse transform at pick time, and for a heavily deformed
part the rest-pose point is not where the author's eye was — mitigated because
opening the annotation restores the clip and time, putting the part back in that
pose.

### D11 — Degradation is a different presentation, not a disabled viewer

With no rendering context, the route renders the still presentation: concept
views, specification, the full annotation list including orphan and partial
states, with triage available. The 3D anchor placement action is present and
stated as unavailable.

*Why:* the annotation data is the valuable part and none of it needs a GPU. A
reviewer on a locked-down laptop can still resolve threads. **Alternative
rejected:** an error page, which makes an entire asset unreachable because of a
driver.

### D12 — Selection, isolation, loop and speed are view state and are never persisted

They live in component state, not in the ViewModel and not in the specification.

*Why:* `asset.yaml` is reviewed in pull requests; a diff caused by someone having
hidden a leg is noise that trains people to stop reading diffs.

## Risks / Trade-offs

- **The shared ViewModel grows a 3D branch** → D2's structural test, plus a
  review rule that any change to `AnnotationViewModel` in this change's diff is a
  design failure to be discussed, not merged quietly.
- **Re-projection drift after a retopology misleads a reviewer** → D5 states the
  distance and flags the annotation; the part is always right even when the point
  is approximate.
- **A large preview stalls a modest laptop** → the preview is already decimated by
  `asset-preview`; the viewer additionally reports the preview's own triangle count
  (labelled as such, per `viewer-3d`) so an unreasonably heavy preview is visible
  as a preview-pipeline problem rather than as "the viewer is slow".
- **Clip names drift from declared states** → D8 surfaces it as a missing clip and
  an unclaimed clip side by side, which is the report a modeller can act on.
- **three.js version churn breaks the scene module** → the dependency is pinned
  and confined behind D1's interface; a version bump is one module's test suite.
- **Rendering context loss on tab switch or GPU reset** → on loss, attempt
  restoration once, restore the camera and the paused clip position, and fall back
  to D11 if restoration fails.
- **Cost accepted overall:** anchors are approximate by construction. The system
  trades exact placement for survivability, and every surface that shows a pin must
  keep saying so — which is why displacement and partial resolution are part of the
  presented state rather than internal detail.

## Migration Plan

Additive, and no schema change: `Anchor3D` was defined in change 1, and the
playback hint (D9) uses fields the format already permits as optional. Existing 2D
annotations are unaffected; an asset with no preview renders the no-preview state
rather than failing. The viewer is a new route in the web app — a deployment that
never links to it is unchanged. Rollback is removing the route: nothing in the
repository was written by this change that the annotation surfaces did not already
write.

## Open Questions

- **The displacement threshold in D5** — a configuration value whose *behaviour* is
  already specified. Needs one calibration pass against a real retopologised asset
  before a default is chosen.
- **Whether an orphan may be re-anchored to a bone directly**, rather than to a
  part with an optional bone. Deferred until a rigged asset has produced an orphan
  in practice; it adds a field to a re-anchor action and changes no stored format.
- **Whether the preview should carry a second, denser variant for close
  inspection.** Only worth answering if reviewers report that decimation hides the
  detail they are reviewing; it is a preview-pipeline decision, not a viewer one.
