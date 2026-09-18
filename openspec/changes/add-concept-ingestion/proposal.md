# Proposal

## Why

Changes 1–3 gave programmers a contract, a validator and an agent surface, and
they did it without asking a single artist to change a habit. That was
deliberate, and it has an expiry date: **an artist has still never opened
CyberCanon.** The first thing she actually does in this product is not write
YAML — it is drag a concept in. Until a concept view lives in the repository next
to `asset.yaml`, there is nothing to pin an annotation on, nothing for a 2D model
sheet to render, and nothing for a vision model to describe.

This change is **roadmap position 4a — the prerequisite for position 4**. The
model sheet is a surface over concept views; specifying the surface before the
views exist would mean inventing the upload path inside a viewer change and
rebuilding it later. It comes now, and not earlier, because the question that
blocked every hosted surface is settled: the API reaches git through a
**persistent working copy per project, fetched on schedule and on webhook, with
write-back as a direct commit to a configured branch**. Ingestion is the first
feature that writes to a game repository from a server, so it is the feature that
proves that decision or exposes it.

The second reason it comes now is that ingestion is where the source-of-truth
rule is most tempting to break. An upload arrives as bytes over HTTP; the easy
implementation stores the bytes in MinIO, writes a row in PostgreSQL, and calls
it a view. That system works for a week and then someone asks why the concept art
is not in the repository with the asset it belongs to. **A view is a file in git,
committed by the person who uploaded it**, and blob storage is a mirror of that
file. Establishing this on the first write keeps the second and third writes
honest.

## What Changes

- **Concept views are files in the repository.** An upload is validated, written
  into the project's working copy at a deterministic path derived from the asset
  and the view slot, and **committed to the configured branch attributed to the
  uploading person** through the `.canon/actors.yaml` mapping. No pull request,
  no service-account author.
- **View slots** — every image occupies exactly one named slot on an asset:
  the canonical `front`, `side`, `back`, or any author-chosen name. Uploading to
  an occupied slot is a *replacement*, never a second file competing for the same
  name.
- **An upload can create the asset.** Targeting an asset id with no `asset.yaml`
  writes a minimal, valid spec — identity and `status: concept`, nothing else —
  in the same commit as the image. It never scaffolds placeholder `design` or
  `constraints` fields, because a spec full of empty fields violates the golden
  rule and teaches people to leave it that way.
- **Uploading does not advance an asset's status.** Adding a view to a
  `validated` asset leaves it `validated`. Status is a human decision; putting an
  image somewhere is not one.
- **Blob storage mirrors, thumbnails derive.** The committed image is mirrored to
  blob storage keyed by content hash, and thumbnails are derived from it. Both are
  rebuildable from the repository alone, and a mirror that is unreachable delays
  a mirror — it never invalidates a committed view.
- **Every replacement is a revision**, because views are files in git. Listing a
  view's revisions, retrieving one, and comparing two side by side are reads over
  git history, not a versioning system this change invents.
- **Replaced views handle their annotations explicitly.** An annotation anchored
  to a view that has been replaced is either **carried** to the new revision or
  **orphaned**, by a stated mechanical rule, and the outcome is visible on the
  annotation. Orphaning is an anchor state, not a third exit: the annotation stays
  open and still owes one of the two exits.
- **Failure leaves nothing behind.** A rejected or failed upload produces neither
  a partial commit nor an orphan blob object. Validation happens entirely before
  the first write, and a multi-image request commits once or not at all.
- **Freshness is observable.** A newly exported render that replaces a view
  becomes visible to someone already looking at it within a bounded interval, or
  what they are looking at is explicitly marked stale. No surface may present a
  superseded image as current.

## Capabilities

### New Capabilities

- `concept-ingestion`: bringing one or more concept views into an asset —
  accepted formats, size and dimension limits, view slots, creating an asset from
  an upload, writing and committing the files attributed to the uploader,
  mirroring to blob storage, deriving thumbnails, freshness of a replaced render,
  and the atomicity that makes a failed upload leave no trace.
- `view-versioning`: the revision history of a view — listing revisions,
  retrieving one, comparing two, the guarantee that superseding never destroys,
  and the explicit carried-or-orphaned outcome for annotations anchored to a
  replaced view.

### Modified Capabilities

None. No earlier change is archived yet, so a delta against an unarchived
capability cannot be written; requirements touching specifications, blobs and
annotations are stated inside the two capabilities above.

## Non-goals

Explicitly **not** in this change:

- **No annotation authoring, rendering or triage.** This change states what
  happens to an annotation when its view is replaced. Creating pins, drawing the
  model sheet, filtering threads and promoting to a rule are
  `annotation-authoring`, `annotation-triage` and `model-sheet-2d`.
- **No model calls of any kind.** Ingestion SHALL complete with model access
  disabled. Generated descriptions, tags and suggested aliases are
  `derived-metadata`, triggered separately by a person or a pipeline after the
  view exists.
- **No HTTP surface, authentication, working-copy mechanics or blob
  infrastructure specified here.** Those are `http-api`, `auth-integration`,
  `hosted-repository`, `blob-storage` and `asset-requests` in `add-web-backend`.
  This change states what ingestion *requires* of them and specifies no transport.
- **No image editing.** No crop, rotate, colour correction, layers, brushes or
  paint-over. What was uploaded is what is committed.
- **No status transitions and no approval workflow.** Ingestion never moves an
  asset along the lifecycle.
- **No bulk folder import, watched directory, or cloud-drive sync.** An
  ingestion request carries the images it carries.
- **No asset deletion and no history rewriting.** Removing a view is a revision;
  nothing in this change can make an earlier revision unreachable.
- **No 3D, no meshes, no exports, no preview GLB.** Concept views are images.
- **No Git LFS requirement.** Size limits keep ordinary concept art comfortably
  within a normal repository; LFS stays a project's own choice.
- **No pull-request write-back, no review gate on an upload.** Settled in
  `project.md`: a direct commit to a configured branch.

## Impact

- **New code** — domain `ViewSlot`, `ConceptView`, `ViewRevision`, `ImageFacts`
  and the carry-forward rule; application ports `ImageInspector` and
  `ThumbnailRenderer`, plus the repository write capability consumed from
  `hosted-repository`; use cases `ingest_views`, `list_view_revisions`,
  `get_view_revision`, `compare_view_revisions`, `reanchor_annotation`; outbound
  adapters for image inspection, thumbnail derivation and content-hash blob keys.
- **New dependency** — an image library behind `ImageInspector` /
  `ThumbnailRenderer` (`Pillow`). The domain gains none: it decides over
  `ImageFacts` exactly as it decides over `MeshFacts`.
- **Configuration** — project-level ingestion limits in `.canon/project.yaml`
  (accepted formats, maximum bytes per image, maximum pixel dimensions) and the
  configured write-back branch, which `hosted-repository` owns.
- **Consumer-side impact** — a game repository gains a `concept/` directory next
  to each asset's `asset.yaml`, holding one image file per view slot, and gains
  commits authored by artists who may never have used git directly. Thumbnails
  and mirrored blobs never enter the repository.
- **Operational impact** — a blob store and thumbnail cache that are both
  droppable: deleting either and rebuilding from the repository is a supported,
  tested recovery, not a hope.
