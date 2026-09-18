# Design

## Context

This is the first change that **writes to a game repository from a server**, and
the first one an artist touches. Everything before it read files or wrote one
alias into `asset.yaml` from the person's own machine. Here bytes arrive over a
network, become a commit authored by someone who may never have run `git` in her
life, and fan out into a mirror and a thumbnail cache that must both be
throwaway.

Two standing decisions from `openspec/project.md` do most of the work. **Git is
the source of truth**, so the commit — not the upload, not the blob — is the
moment a view exists. And **the hosted API reaches git through a persistent
working copy per project with write-back as a direct commit to a configured
branch**, which `hosted-repository` (`add-web-backend`) owns; this change consumes
that and adds no second git mechanism.

One boundary from change 1 is reused deliberately rather than re-argued: mesh
*rules* are domain and mesh *reading* is a port. Images get the same treatment.
See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**

- Make the commit the only thing that counts, so that every derived artifact is
  provably rebuildable and no failure can produce a half-ingested view.
- Keep attribution real: an artist's name in `git blame`, not a service account.
- Answer "what happened to my pins?" with a rule, in writing, before anyone can
  be surprised by it.
- Keep ingestion runnable with no blob store, no thumbnails and no model, because
  that configuration is the local one and it must keep working.

**Non-Goals (design level):**

- No background job queue, no worker pool. Mirroring and thumbnails are
  synchronous after the commit, with a retry pass for what was pending.
- No content-based image analysis of any kind — no perceptual hashing, no
  similarity, no feature matching. Every decision here is made from dimensions,
  bytes and hashes.
- No storage tiering, no CDN policy, no signed-URL scheme. `blob-storage` owns
  how bytes are served.
- No multi-writer concurrency model beyond serialising writes per project working
  copy.

## Decisions

### D1 — Image reading is a port; image rules are the domain, over `ImageFacts`

`ImageInspector` takes bytes and returns a frozen `ImageFacts` value object
(`format`, `width`, `height`, `byte_size`, `content_hash`, `has_alpha`). The
domain decides accepted/rejected against the project's `IngestionLimits`, and the
domain computes the aspect ratio that D6 depends on.

*Why:* it is exactly the `MeshFacts` boundary that made the entire validator test
suite run with zero files on disk, and the same payoff applies — every format,
size, slot and carry-forward test is a constructed `ImageFacts`.
**Alternative rejected:** calling the image library directly inside the use case,
which is three fewer files and makes every limit test need a real JPEG.
**Cost accepted:** a value object and an adapter for six fields, plus the
discipline that anything the domain needs to know about an image must first become
a field on `ImageFacts`.

### D2 — The commit is the transaction boundary; order is validate → stage → commit → mirror → derive

Nothing is written until every image and slot in the request has passed. Then all
files for the request are staged and committed once. Only after the commit
succeeds does anything reach blob storage or the thumbnail cache.

*Why:* it makes `concept-ingestion`'s atomicity requirement structural rather than
a cleanup routine. A failure before the commit has nothing to undo; a failure after
it has nothing to undo either, because the commit is the answer and the mirror is
derivable. **Alternative rejected:** mirroring first so a thumbnail can be shown
while the commit runs — it shaves a moment off the upload and buys an orphan blob
every time a commit fails, which is precisely the "neither a partial commit nor an
orphan blob" the spec forbids. **Cost accepted:** the mirror lags the commit, so
the surface must be able to serve a just-committed view from the working copy;
this is also why "awaiting mirroring" is a specified, ordinary state rather than
an error.

### D3 — Blob keys are content hashes; the hash → (asset, slot, revision) map lives in the rebuildable index

A mirrored object is stored under its content hash. Which asset, slot and revision
that hash belongs to is a row in the PostgreSQL index, written when the commit is
observed and reconstructible by walking the repository.

*Why:* it makes mirroring idempotent (re-mirroring writes nothing new), makes an
identical image uploaded to two assets cost one object, and makes orphan collection
a set difference against the repository. **Alternative rejected:** keying by
`asset/slot/revision`, which is self-describing and human-browsable in MinIO but
duplicates bytes and turns a re-mirror into a write. **Cost accepted:** a bucket
full of hash-named objects is unreadable without the index — acceptable precisely
because the index is rebuildable and the repository is the truth.

### D4 — A view is one file per slot at a deterministic path, replaced in place

`<asset dir>/concept/<slot>.<ext>`. Replacing a view writes the same path, which is
what makes git produce a revision rather than an unrelated file.

*Why:* `Anchor2D{view, u, v}` from change 1 keys on the slot name, so the slot must
be a stable address. **Alternative rejected:** revision-numbered filenames
(`front_v2.png`), which make "current" ambiguous, break the anchor's key, and
reimplement inside the filesystem the versioning git already provides.
**Cost accepted:** a slot whose format changes also changes its extension, so the
path moves; ingestion handles this as a rename of the old path followed by the
write, so history follows the slot instead of showing a delete and an unrelated
add.

### D5 — Attribution is a precondition, not a fallback

The acting person is resolved from the credential to an `Actor`, then through
`.canon/actors.yaml` to a git author, **before** validation of the images. No
mapping, no ingestion; the refusal names the file and the unmapped subject.
`Attribution(actor, via)` from change 2 carries the agent slot for
agent-mediated uploads.

*Why:* the alternative is what every system does under deadline — commit as
`cybercanon-bot <noreply@…>` with the real person in a trailer — and then
`git blame` on the studio's concept art says "bot" forever. `project.md` calls
retroactive identity mapping "ruinous to reconstruct after six months"; this is the
first place that bill comes due. **Alternative rejected:** a service-account author
with a `Co-authored-by` trailer. **Cost accepted:** onboarding an artist requires a
mapping entry before her first upload, which is a support interaction on day one,
mitigated by an error that names the exact file and the exact missing key.

### D6 — Carry-forward is decided by aspect ratio, in the domain, and marked on the annotation

On replacement, each annotation anchored to the slot is carried if
`|new.aspect − old.aspect| ≤ tolerance`, else orphaned. Carried annotations record
the revision they were authored against and are rendered with that fact visible.

*Why:* the common case by far is re-exporting the same board at the same ratio,
where orphaning every pin would punish exactly the behaviour the product wants
(re-export often, keep the canon fresh). A normalised `u,v` anchor stays meaningful
under a pure rescale and stops being meaningful under a crop or a reframe, and
aspect ratio is the cheapest honest proxy for that distinction.
**Alternatives rejected:** *always orphan* — safe, trivially correct, and it
teaches artists that replacing a view destroys feedback, so they stop replacing
views; *image-similarity re-projection* — it would move pins by inference, which is
the "silently mis-placed annotation" `project.md` forbids by name, dressed up as a
feature. **Cost accepted:** a same-ratio replacement whose content is completely
different carries pins to meaningless places. Mitigated, not solved, by showing the
authoring revision on every carried pin so a reader can see the pin predates what
he is looking at — and by D7, which keeps the annotation open either way.

### D7 — Orphaning is a third *anchor state*, never a third *exit*

`AnchorState ∈ {carried, orphaned}` is independent of the annotation's exit state
`{open, promoted, resolved}`. Nothing in ingestion may write the exit state.

*Why:* the two-exit discipline is the rule that keeps `art-spec.md` from rotting,
and auto-resolving orphans would be a way to empty the open-issues list without
anybody deciding anything — the failure mode the discipline exists to prevent,
arriving through a side door. **Alternative rejected:** treating an orphan as
resolved-by-obsolescence. **Cost accepted:** orphans accumulate until a human
triages them, which is visible and fixable; the invisible alternative is not.

### D8 — Freshness is a revision token the client can compare; the transport is polling

Every view reference carries the content hash of the revision being shown. A
surface asks for the current token for the views it displays and re-fetches when it
differs. The interval is configuration.

*Why:* the observable requirement — new revision within a bounded interval, or
marked stale — is satisfiable with no new infrastructure, and the "marked stale"
half of it is what makes a failed poll a correct outcome rather than a bug.
**Alternative rejected:** a server-sent-event or WebSocket channel now, which is
strictly better for an artist re-exporting every ninety seconds and drags in
connection lifecycle, reconnection and an open socket per viewer for a feature
nobody has used yet. Deferred behind the same token, which a push transport would
carry unchanged. **Cost accepted:** up to one interval of staleness, and a poll per
open view; both bounded and both configuration.

### D9 — Thumbnails are never written into the working copy

Derivation reads the committed bytes and writes only to blob storage. Nothing is
`.gitignore`d because nothing is there to ignore.

*Why:* a `.gitignore` entry is a rule someone can violate; a code path that never
writes to the working tree cannot. Committed thumbnails would also mean binary
churn in every review of every concept change. **Alternative rejected:** a
git-ignored `.canon/thumbs/` cache in the working copy, which would be faster
locally and would make the "working copy is clean after a failed upload" check
ambiguous. **Cost accepted:** a wiped blob store costs a re-derivation pass over
the project before thumbnails are available again.

### D10 — Creating an asset writes identity and status only

`ingest_views` on an unknown asset id writes `id`, `name`, `status: concept` and
nothing else.

*Why:* the golden rule — every design field must constrain art, constrain code, or
be checkable. A scaffolded spec with empty `design` and `constraints` blocks
contains only fields that do none of the three, and the empty scaffold is what
people leave behind. **Alternatives rejected:** *refusing to upload without a
pre-existing asset*, which makes the first five minutes of the product a YAML
exercise; *scaffolding a template with commented placeholders*, which produces a
file whose diff is 40 lines of comments the first time anyone edits it.
**Cost accepted:** assets created this way are deliberately thin, and something
later has to prompt their owners to fill them in — a surface concern, not a
schema one.

### D11 — Writes are serialised per project working copy, and the slot's current hash is re-checked before committing

One writer at a time per working copy; the use case re-reads the target slot's
current content hash inside the critical section and refuses if it changed since
the request was prepared.

*Why:* a persistent working copy is shared mutable state and two artists replacing
`front` within the same second is an ordinary Friday. **Alternative rejected:**
optimistic write plus conflict resolution, which for binary files has no merge and
would silently pick a winner. **Cost accepted:** ingestion throughput per project
is one commit at a time, which at studio scale is irrelevant, and the loser of a
race gets an explicit "this slot changed while you were uploading" rather than a
lost image.

### D12 — The prohibition on model calls during ingestion is a test

A structural test asserts the ingestion use-case package imports neither `LLMPort`
nor `VisionPort`, and a behavioural test runs a full ingestion with both ports
wired to fakes that raise on any call.

*Why:* "ingestion must not call a model" is an absence, and change 2's D6 already
established that an absence enforced by absence lasts until the first person who
thinks auto-describing on upload would be a nice touch. **Alternative rejected:**
a note in the proposal. **Cost accepted:** one more structural test to maintain.

## Risks / Trade-offs

- **Repository bloat from binary revisions.** Every replacement adds a full image
  blob to history, and concept art gets replaced often → Size and dimension limits
  are enforced *before* the write, one file per slot keeps the count bounded, and
  Git LFS stays available as a project's own choice. This change does not require
  LFS, because requiring it would make adopting CyberCanon a repository migration.
- **Artists work in PSD, TIFF and layered formats that the accepted set excludes**
  → The rejection names the accepted formats, and `links` already holds a pointer
  to the source document. Accepting layered sources would mean either flattening
  them (an image operation this change refuses to own) or serving a format no
  browser renders.
- **The aspect-ratio carry rule is a heuristic and will occasionally be wrong** →
  D6's mitigation: every carried pin shows the revision it was authored against,
  and D7 keeps it open and triageable. The rule is stated in the specification so
  it is a documented behaviour rather than a surprise.
- **The working copy is behind the remote when a commit is attempted** → Fetch and
  fast-forward inside the critical section; on a non-fast-forward, refuse the
  ingestion and report it rather than force anything. `hosted-repository` owns the
  fetch schedule; ingestion only requires that it can demand one before writing.
- **The index's hash → view mapping drifts from the repository** → It is
  rebuildable by definition and the rebuild is a specified, tested operation. Any
  read that cannot find a mapping falls back to the repository rather than
  reporting the view as missing.
- **Cost accepted overall:** ingestion is slower than a direct object-store upload,
  by a commit. That latency buys the property the product is built on — the concept
  art is in the repository, next to the asset, in the artist's name.

## Migration Plan

Additive. A repository with no concept views is unaffected; the `concept/`
directory appears next to an asset's `asset.yaml` the first time a view is
ingested for it. No existing file changes format and no migration runs against a
game repository.

The index gains tables for views, revisions and the hash mapping, created by a
migration that is droppable and rebuildable like the rest of the index. Blob
storage gains a bucket.

Rollback is turning the ingestion surface off: the committed views stay in the
repository, which is the entire point — a project that stops using CyberCanon
keeps its concept art exactly where it already lives.

## Open Questions

- **Whether a slot may carry a link to its layered source document** (a `.psd` or
  `.kra` in `links`) alongside the flattened view. Additive; it adds a field and
  changes no requirement here.
- **The default freshness interval and the aspect-ratio tolerance.** Both are
  configuration values whose behaviour is already specified; only their defaults
  are open, and they want real usage to set them.
- **Whether orphaned-annotation counts should surface as a badge in the asset
  browser.** Presentation, decided when `model-sheet-2d` and `annotation-triage`
  land.
