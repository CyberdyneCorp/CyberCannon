# Proposal

## Why

Changes 1–3 gave the project a contract (`asset.yaml`), a machine that enforces
it (`canon validate`), and an agent surface that reads it. All three were
deliberately usable **without a single artist changing a habit** — which is also
their limit. The spec file now says what an asset must be; nothing yet lets the
people who actually decide what it must look like *argue against the image* and
have the conclusion land in that file.

Today that argument happens in Discord, over a screenshot, with an arrow drawn in
a screenshot tool. The conclusion — "the shoulder pauldron reads as a backpack at
15 m" — is stated once, agreed once, and then lost, because nothing carries it
into the contract an agent or a contractor reads three months later. The cost is
the same one the project exists to kill: art direction that is real but not
written down, so the mesh is wrong at integration time and nobody is at fault.

This is **roadmap position 4**, the first artist-facing interface, and it comes
now rather than earlier for a specific reason stated in `openspec/project.md`:
the artist-facing surfaces arrive when spec files **already exist and have proven
their value**. Annotating an asset that has no contract produces comments; that
is a chat app. Annotating an asset that has a contract produces **rules**, because
there is somewhere for a durable conclusion to go.

It is 2D and not 3D on purpose. A concept view is a flat image with a stable
coordinate system, so the anchoring problem is trivial there, while the parts that
are genuinely hard and genuinely valuable — threads, filtering, the two-exit
triage, attribution, the write path back into git — are **medium-agnostic**. This
change builds those once, against the easy medium, so that change 5 (`add-viewer-3d`)
adds a renderer and an `Anchor3D` rather than a second annotation system.

## What Changes

- **Annotation authoring as a behaviour** — the annotation *entry* already exists
  in `asset-spec`; this change specifies creating one against a 2D view anchor or
  a 3D part anchor, choosing its `kind` (`art-direction | technical | design`),
  replying in a thread, and editing or deleting one's own contribution.
- **Everything except anchor construction is medium-agnostic.** Threading,
  filtering, status, permission and triage are specified so that they hold
  identically for an `Anchor2D` and an `Anchor3D`. `add-viewer-3d` inherits them
  unchanged.
- **The two exits, which are the product.** **Promote** moves an annotation's
  content into `constraints` or `concept.silhouette_rules` as a durable rule and
  retires the annotation; **resolve** archives it as a transient issue and
  excludes it from the compiled briefing. There is no third exit and no
  accumulating comment log.
- **Promotion is an art director's act, and only a person's act.** Anyone may
  annotate; only an art director may promote; promotion is never callable by an
  automated caller, for any role — an agent raising a budget so its own output
  passes is how trust dies in week two.
- **Promotion produces a reviewable commit.** A promoted rule is a normal, small
  diff to `asset.yaml` on the configured branch, attributed to the acting person
  through the `.canon/actors.yaml` mapping — reviewable with `git show`, not a
  row in a table.
- **The periodic triage pass** — an art director's queue of open annotations for a
  project, ordered so that recurring feedback surfaces as a promotion candidate.
  This is the loop that makes a team converge instead of recording its
  disagreements more neatly.
- **The 2D model sheet** — an asset's views, pins placed with a pointer or an
  Apple Pencil, **normalized coordinates independent of zoom and display size**,
  filtering and selection by kind and open/resolved state, a thread panel, and a
  simple freehand scribble over a view for "this edge, not that one".
- **The view's only job is turning input into an `Anchor`.** Everything else lives
  behind a shared annotation model that is tested with no DOM.
- **Attribution names the person, and the agent when one acted** — "rafa, via
  blender-agent". Identity comes from the credential; it is never a request
  parameter.

## Capabilities

### New Capabilities

- `annotation-authoring`: creating an annotation against either anchor form,
  its kind, threaded replies, editing and deleting one's own contribution, who
  may do what, orphan behaviour, and attribution to the person and to the agent
  when one acted.
- `annotation-triage`: the two exits — promote to a durable rule and resolve as a
  transient issue — who may take each, the art director's periodic triage pass,
  the guarantee that the compiled briefing never grows from resolved annotations,
  and the reviewable commit a promotion produces.
- `model-sheet-2d`: the sheet itself — displaying an asset's views, pin placement
  by pointer or Apple Pencil, resolution-independent normalized coordinates,
  selection and filtering, the freehand scribble layer, the thread panel, and the
  rule that the view produces an anchor and nothing more.

### Modified Capabilities

None. No earlier change is archived yet, so a delta against an unarchived
capability cannot be written. Requirements that extend an annotation entry with
its thread and its scribble geometry, and that exclude retired annotations from a
compiled briefing, are therefore stated inside `annotation-authoring` and
`annotation-triage` rather than as deltas against `asset-spec` and
`spec-compilation`.

## Non-goals

Explicitly **not** in this change:

- **No 3D viewer.** No `three.js`, no mesh loading, no camera, no part picking.
  `add-viewer-3d` owns `viewer-3d`, `anchor-resolution` and `animation-playback`;
  this change only guarantees that nothing it specifies has to be rewritten there.
- **No paint-over tool.** No brushes, no layers, no opacity, no colour picking, no
  blend modes — `project.md` defers full paint-over, and the scribble here is a
  pointing gesture, not a painting surface.
- **No HTTP surface, no authentication, no repository write transport.** Those are
  `http-api`, `auth-integration` and `hosted-repository` in `add-web-backend`; this
  change consumes them.
- **No concept view ingestion or view versioning.** Uploading, deriving and
  versioning the images the sheet displays belong to `concept-ingestion` and
  `view-versioning` in `add-concept-ingestion`.
- **No MCP write tools.** `add_annotation` over MCP is `mcp-write-surface` in
  `add-mcp-writes`. This change specifies what attribution and authorization an
  agent-originated annotation must satisfy, so that change is a transport.
- **No notifications, no mentions, no email, no presence or live cursors.** A
  second person's annotation becomes visible on the next fetch; realtime
  collaboration is not required for a team of this size.
- **No annotation on anything but an asset's views and parts.** Not on a compiled
  briefing, not on a document in CyberArche, not on a validation report.
- **No mass-variation triage or voting**, deferred by `project.md`.
- **No database-authoritative annotations.** An annotation that exists only in the
  index and not in the repository is a bug, not a feature.

## Impact

- **New domain code** — `Anchor2D`, the annotation thread and reply value objects,
  `AnnotationFilter`, the promotion target (`constraints` vs
  `concept.silhouette_rules`), and the triage policy deciding who may promote,
  resolve and reopen.
- **New application code** — use cases `create_annotation`, `reply_to_annotation`,
  `edit_annotation`, `delete_annotation`, `list_annotations`, `promote_annotation`,
  `resolve_annotation`, `reopen_annotation`, `list_triage_queue`; all writing
  through the existing `SpecStore` port, extended with an attributed commit.
- **New frontend code** — `apps/cybercanon/web`: one `AnnotationViewModel`
  (`*.svelte.ts`, module singleton plus `createAnnotationViewModel()` factory for
  tests) shared by this change and `add-viewer-3d`, the `Sheet2D` view, the thread
  panel, the filter bar, and typed clients under `lib/api/`. Views never call the
  API directly.
- **Consumer-side impact** — an annotated asset's `asset.yaml` grows threaded
  annotation entries while issues are open and **shrinks again** as they are
  resolved or promoted; a promoted rule appears as a small diff in `constraints` or
  `concept.silhouette_rules`, authored by the art director who promoted it. Repos
  see more commits on the configured branch, each one legible.
- **Testing impact** — the annotation model is covered without a DOM and without a
  GPU, and the same suite is re-run against an `Anchor3D` fixture in change 5 to
  prove the medium-agnostic claim structurally rather than by assertion.
