# Design

## Context

Changes 1–3 produced a contract, a validator and a read-only agent surface. This
change is the first one a person who is not a programmer ever opens, the first
Svelte code in the repository, and — more consequentially — the **first write path
from a hosted surface back into the game repository**. Every earlier change read
`asset.yaml`; this one changes it while someone is looking at a picture.

It consumes `http-api`, `auth-integration` and `hosted-repository` from
`add-web-backend` (the persistent working copy per project, fetched on schedule
and webhook, written back as a direct commit to a configured branch attributed
through `.canon/actors.yaml`), and the views it displays come from
`concept-ingestion` and `view-versioning` in `add-concept-ingestion`. It defines
neither.

Two constraints from `openspec/project.md` govern everything below: **annotations
have exactly two exits**, and **git is the source of truth** — an annotation that
lives in PostgreSQL and is "synced" later is the design this project exists to
avoid. A third, from the frontend convention: MVVM is used **selectively**, and
this change is the one place it was promised to pay off.

See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**

- Build the medium-agnostic annotation core **once**, against the easy medium, so
  `add-viewer-3d` adds a renderer rather than a second annotation system.
- Make the two exits the obvious thing to do, and make a promotion look like a
  reviewable commit rather than a database row.
- Keep the durable truth in `asset.yaml` even though a UI is writing it.
- Keep pin coordinates meaningful across zoom, display size and device.

**Non-Goals (design level):**

- No realtime collaboration, no presence, no operational transform. Two artists
  annotating the same asset at the same second is a retry, not a protocol.
- No offline authoring. The sheet is a hosted surface; the offline story is the
  CLI, which deliberately has no identity and therefore cannot attribute a write.
- No pin clustering algorithm. A view with enough pins to need clustering is a
  triage failure, and the queue is the fix.

## Decisions

### D1 — One `AnnotationViewModel`, two views; a view's only product is an `Anchor`

A single module-singleton ViewModel (`annotation-view-model.svelte.ts`, with a
`createAnnotationViewModel()` factory for tests) owns selection, filter state,
draft composition, thread expansion and exit invocation. `Sheet2D` supplies
`Anchor2D{view, u, v}`; `Viewer3D` will supply `Anchor3D{part, bone?, point,
normal, camera}`. The ViewModel accepts an `Anchor` and never learns which
produced it.

*Why:* this is the claim in `project.md` that makes "support 2D and 3D" cost far
less than twice, and the whole justification for building 2D first.
**Alternative rejected:** a `Sheet2DViewModel` and a `Viewer3DViewModel` over a
shared service — which reads better per file and guarantees that filtering and
triage drift, because the two will be written three months apart.
**Cost accepted:** the ViewModel may not touch a DOM type, a canvas context or a
`three.js` object, so pixel and ray maths live in the views and are tested
separately. A test imports the ViewModel in an environment with no DOM to keep
that honest.

### D2 — MVVM here, plain components everywhere else

The asset browser, the spec editor and every form stay plain `.svelte` components
with runes and typed clients under `lib/api/`. Only annotation gets a ViewModel.

*Why:* runes are already a binding layer, so a ViewModel per component buys
nothing but indirection. MVVM earns its keep under exactly one condition — **one
state machine, more than one view** — and annotation is the only place in
CyberCanon where that holds. **Alternative rejected:** MVVM everywhere, for
consistency; it would add a file and a layer per form and make the codebase
slower to change for no test benefit. **Cost accepted:** two idioms in one
frontend, mitigated by the naming rule (`*.svelte.ts` is a ViewModel, and there
is one) and by a review rule that a new ViewModel must name its second view.

### D3 — `Anchor` is a domain value object; the pixel maths never crosses into it

Domain: `AnchorKind`, `Anchor2D(view_name, u, v)` with `u, v ∈ [0, 1]` validated
at construction, `Anchor3D` as already specified, `Annotation`, `Reply`,
`AnnotationKind`, `AnnotationState`, `AnnotationFilter`, `PromotionTarget`,
`TriageEntry`, `Stroke` (an ordered list of normalized points), and `Attribution`
(introduced in change 2). Adapter and view: everything involving a bounding
rectangle, a device pixel ratio, a zoom transform or a rendition scale.

*Why:* a normalized coordinate is a fact about the image; a pixel is a fact about
a display that existed for one afternoon. Putting the conversion in the view is
what makes "independent of zoom and display size" a structural property rather
than a bug someone fixes twice. **Cost accepted:** the view owns a small,
genuinely fiddly coordinate transform, and it needs its own focused tests
(round-trip a coordinate through zoom and pan and assert equality within float
tolerance).

### D4 — Threads live in `asset.yaml`. There is no annotation table.

Annotations, replies, attribution, anchors and strokes are written into the
asset's specification file through `SpecStore`. PostgreSQL holds a projection for
the triage queue and for listing; it is rebuilt from the repository and is never
read as the truth for a thread.

*Why:* `project.md` forbids a database that is authoritative, and annotation is
precisely where that temptation is strongest, because annotations look like
application data. They are not: a promoted rule and the argument that produced it
belong in the same history as the constraint it became. **Alternative rejected:**
annotations in PostgreSQL flushed to git on promotion — which gives fast writes, a
clean `asset.yaml`, and a system where losing the database loses every open issue.
**Cost accepted:** a commit per annotation and per reply, and a write path that is
as slow as a git commit and push.

### D5 — Writes are serialized per asset and reconciled by base revision

Each write reads the asset's current revision, applies the change to the parsed
specification, re-serializes preserving comments, and commits with the revision it
started from. A commit whose base no longer matches is retried once by re-reading
and re-applying the same domain operation; a second failure is reported to the
person with their text preserved.

*Why:* two artists annotating the same asset is ordinary, and a lost annotation is
worse than a visible retry. Applying the *operation* rather than the *file* means
two people adding different annotations both succeed. **Alternative rejected:**
locking the file per asset, which fails badly when a browser tab is closed mid-edit.
**Cost accepted:** the write path needs an idempotency key so a retried request does
not create two annotations; it is the client-generated annotation id.

### D6 — Promotion is one use case producing one atomic commit, validated first

`promote_annotation(asset, annotation_id, rule_text, target, actor)` authorizes,
writes the rule into `constraints` or `concept.silhouette_rules`, retires the
annotation, runs the existing structural validation over the **resulting**
document, and only then commits — once, containing both edits.

*Why:* the spec forbids a state where the rule exists and the annotation is still
open. Two operations across two commits produce exactly that state whenever the
second fails. Validating before the commit means the system never writes a file
its own validator rejects, which would strand the asset for the CLI users.
**Alternative rejected:** write-then-retire with compensation, which is a
distributed transaction for a single file.

### D7 — Promotion is exposed by the HTTP surface only, and by nothing else

Not an MCP tool (change 2's exact tool-set test is extended to keep it out), and
not a `canon` subcommand.

*Why:* the two exits are attributed acts, and attribution requires an identity —
but `project.md` requires that the CLI never need one. A `canon promote` would
either break that rule or write unattributed durable rules, and unattributed rules
are how "who decided this?" becomes unanswerable six months in. **Alternative
rejected:** a CLI promote reading a local git identity, which quietly becomes a
second, weaker identity system. **Cost accepted:** an art director without the web
app promotes by editing `asset.yaml` in a normal commit — which is the same
outcome, reviewed the same way, and is a feature rather than a workaround.

### D8 — A scribble is normalized polylines in the annotation, never a raster

Each stroke is an ordered list of `[u, v]` pairs in the view's image space,
simplified with a fixed tolerance before writing and capped at a configured point
count per annotation. No width, no colour, no layer, no z-order.

*Why:* the data shape is the guardrail. Storing a PNG overlay in blob storage
would make brushes, opacity and layers a feature request away, would produce an
un-reviewable diff, and would tie a stroke's meaning to the rendition resolution it
was drawn at. Polylines scale with zoom for free and delete cleanly with their
annotation. **Alternative rejected:** the raster overlay. **Cost accepted:** this
can never become the paint-over tool an art director may eventually want, which is
correct — `project.md` defers that deliberately.

### D9 — Server state lives in a query cache; the ViewModel holds only client state

Fetched annotations are cached per `(project, asset, revision)`. The ViewModel
holds selection, filter, draft text, draft strokes and pending-write state, and
reads the list from the cache. A mutation optimistically inserts into the cache
entry, then invalidates that asset's entry on settle; a failure removes the
optimistic entry and surfaces the error with the draft intact.

*Why:* `project.md` states server state lives in a query cache, not scattered
across ViewModels — and here the reason is concrete: the 3D viewer and the sheet
will be open on the same asset, and two copies of the annotation list would drift
the moment one of them writes. **Alternative rejected:** the ViewModel owning the
fetched list, which is simpler until the second view exists. **Cost accepted:** an
explicit invalidation key discipline; forgetting one shows up as a stale pin,
which the reload scenario in `model-sheet-2d` tests for.

### D10 — One input path: Pointer Events, with `pointerType` deciding intent

Pen places pins and draws; mouse and trackpad place pins; touch pans and zooms
once a pen has been seen in the session, and places pins when it has not.

*Why:* it is one code path for four input devices, and it makes palm rejection a
state flag rather than a heuristic. **Alternative rejected:** separate mouse and
touch handlers with a stylus-specific path, which triples the surface where the
coordinate transform can be got wrong — and the transform is the one thing this
view must not get wrong. **Cost accepted:** a session-scoped "pen seen" flag is a
small piece of mode, and it is reset per sheet.

### D11 — The triage queue is computed from specifications, accelerated by the index

`list_triage_queue(project, filter)` reads open annotations through `SpecStore`
and computes counts and ordering in the domain. The PostgreSQL projection exists
to avoid re-parsing every specification per request, and a request served from it
is verified against the file's content hash exactly as `asset-lookup` already
requires.

*Why:* the capability requires the queue to be derivable from the repository
alone, and making that the real implementation rather than a fallback means the
fallback is tested every time. **Cost accepted:** a cold queue on a large project
parses every specification once.

### D12 — The medium-agnostic claim is enforced by a parameterized suite, not by intent

The annotation core's test suite is parameterized over an anchor factory. This
change runs it with a 2D factory and with a **3D stub factory**; `add-viewer-3d`
replaces the stub with the real one and adds no cases.

*Why:* "these behaviours are identical for both anchor forms" is a specification
statement in two capabilities here, and a statement like that decays silently.
Parameterizing makes the 3D change's cost visible on day one: if change 5 has to
add a case to this suite, the shared core was not shared. **Alternative rejected:**
asserting it in review, which is how the CLI and MCP renderers would have drifted
had change 2 not done the same thing.

## Risks / Trade-offs

- **A commit per reply makes repository history noisy** → Annotation commits carry
  a distinct message prefix naming the asset and annotation id, so they are
  filterable in a log and in a blame; and the file shrinks as threads take their
  exits, which is exactly the two-exit rule paying rent. If it still hurts, D-open
  question 1 (coalescing a session's replies) is a configuration change, not a
  redesign.
- **Two people annotate one asset simultaneously and one write is lost** → D5's
  base-revision check with operation replay; a lost write is a reported failure
  with the text preserved, never a silent drop. A regression test drives two
  concurrent creates against one asset and asserts both exist.
- **Comment-preserving round trip damages a hand-authored `asset.yaml`** → Writes
  go through the comment-preserving YAML round trip already used by the CLI, and a
  test asserts that adding an annotation leaves every unrelated line
  byte-identical. This is the risk most likely to lose a team's trust in one
  afternoon.
- **The ViewModel accretes 2D-specific state** and change 5 forks it → D1's
  no-DOM import test, plus D12's parameterized suite. A 2D-specific field cannot be
  added without the 3D parameterization failing to construct.
- **Apple Pencil and touch behave differently across tablet browsers** → One
  Pointer Events path (D10), a documented device test on the target iPad before
  release, and a degradation rule: with no pen seen, touch places pins, so the
  sheet is never unusable on a tablet.
- **The scribble becomes a paint-over request within a month** → The stored shape
  makes it a format change rather than a UI change (D8), so the deferral in
  `project.md` gets an explicit decision rather than an accidental one.
- **The hosted repository is unreachable when someone annotates** → The write fails
  visibly and the draft is preserved; nothing is queued into browser storage and
  presented as recorded. A pin the repository does not have must not appear after a
  reload, which `model-sheet-2d` specifies.
- **Cost accepted overall:** annotation writes are as slow as a git commit and push,
  in exchange for feedback that survives the database being deleted and that an art
  director can review with `git show`.

## Migration Plan

Additive. The annotation entry defined in `asset-spec` gains two optional members —
an ordered reply list and a stroke list — so a specification file written before
this change parses unchanged and a file written after it is still read correctly by
the existing CLI and MCP surfaces. Nothing in the validation, compilation or lookup
paths changes behaviour for an asset with no annotations.

Rollback is removing the sheet's route from the web application: no specification
file needs to be rewritten, and annotations already committed remain valid content
read by `canon compile` and by the MCP read tools.

## Open Questions

- **Whether a session's replies should coalesce into one commit** after a quiet
  period, rather than one commit each. A configuration value over the same write
  path; the durability guarantee it governs is already specified.
- **Whether the triage queue needs pagination** above some number of open
  annotations per project. It changes a response shape and no specified behaviour;
  the honest signal to revisit it is a project whose queue does not fit one screen
  of the art director's pass.
- **Where a rule that applies to every asset in a project should land** when an art
  director promotes one — today it is written to the asset being viewed, and a
  project-level rule is authored directly in the project configuration. A
  project-scoped promotion target is a later capability, not a gap in this one.
