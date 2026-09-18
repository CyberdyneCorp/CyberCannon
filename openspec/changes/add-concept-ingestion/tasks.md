# Tasks

## 1. Domain — views, slots and image facts

- [ ] 1.1 Model `ViewSlot` with the canonical names `front`/`side`/`back` and the arbitrary-name rule (lowercase alphanumeric plus underscore, leading letter or digit, ≤32 characters); verify accepted and rejected names including `Front View!` and a 33-character name
- [ ] 1.2 Implement `ImageFacts` as a frozen value object (`format`, `width`, `height`, `byte_size`, `content_hash`, `has_alpha`) and verify `lint-imports` still reports zero third-party imports in `libs/cybercanon/domain`
- [ ] 1.3 Implement `IngestionLimits` (accepted formats, maximum bytes, maximum dimension) merged from project configuration with defaults, and verify override, fallback and neither-declared cases
- [ ] 1.4 Implement the acceptance rules as pure functions over `ImageFacts` (`format.unsupported`, `size.exceeded`, `dimension.exceeded`) and verify over-limit, at-limit and under-limit cases from hand-built facts with no files on disk
- [ ] 1.5 Model `ConceptView` and `ViewRevision` (revision identifier, content hash, dimensions, byte size, author, time, current flag) and verify a listing of three revisions marks exactly one current
- [ ] 1.6 Implement the deterministic view path function (asset directory + slot + extension, D4) and verify the same slot always yields the same path and that a format change yields a rename pair rather than an unrelated path
- [ ] 1.7 Implement the carry-forward decision as a pure function over two `ImageFacts` and a tolerance (D6) and verify carried on equal aspect ratio, carried within tolerance, and orphaned on a crop
- [ ] 1.8 Add `AnchorState` (`carried`/`orphaned`) to the annotation model independently of the exit state, and verify by test that no ingestion code path can set `promoted` or `resolved` (D7)

## 2. Application — ports and the ingestion use case

- [ ] 2.1 Define the `ImageInspector` port (bytes → `ImageFacts`) and the `ThumbnailRenderer` port (image bytes + size set → derived bytes), each with an in-memory fake under `application/testing/`; verify port-conformance tests run against the fakes
- [ ] 2.2 State the repository write capability ingestion requires of `hosted-repository` (stage explicit paths, fetch, commit as a resolved author on the configured branch, read a file's revision history) as a port protocol with a fake; verify the fake satisfies every ingestion test with no git binary present
- [ ] 2.3 Extend `BlobStore` with content-hash keyed put/exists (D3) and verify that mirroring the same bytes twice writes once
- [ ] 2.4 Implement attribution resolution as a precondition (credential → `Actor` → git author via `.canon/actors.yaml`, D5) and verify an unmapped person is refused before any image is inspected and before any path is written
- [ ] 2.5 Implement `ingest_views` in the fixed order validate → stage → commit → mirror → derive (D2) and verify a single request for three slots produces exactly one commit containing three files
- [ ] 2.6 Implement asset creation on ingestion writing identity and `status: concept` only (D10) and verify the created specification has no `design` or `constraints` key and appears in the same commit as the image
- [ ] 2.7 Verify ingestion never changes `status`: a test ingests into assets at `concept`, `modeling` and `validated` and asserts each status is unchanged
- [ ] 2.8 Implement per-request rejection semantics and verify that one oversized image among three produces no commit, no blob object, and a report naming the offending image, its observed size and the allowed size
- [ ] 2.9 Implement duplicate-slot detection within one request and verify two images naming `side` are rejected naming the slot
- [ ] 2.10 Implement identical-content short-circuit and verify that re-uploading byte-identical bytes to a slot creates no revision and reports the view unchanged
- [ ] 2.11 Implement per-working-copy write serialisation with a pre-commit re-check of the slot's current hash (D11) and verify two concurrent ingestions into one slot produce one commit and one explicit "slot changed" refusal

## 3. Adapters — image inspection, thumbnails and mirroring

- [ ] 3.1 Implement the `ImageInspector` adapter detecting format from content, not extension, and verify a TIFF named `.png` is reported as TIFF
- [ ] 3.2 Implement the `ThumbnailRenderer` adapter deterministically (fixed size set, fixed encoder settings, D9) and verify two derivations of the same source produce identical content hashes
- [ ] 3.3 Verify thumbnails never reach the working copy: a test ingests a view and asserts the commit and the working tree contain no thumbnail file
- [ ] 3.4 Implement the mirror pass writing content-hash keyed objects and recording the hash → (asset, slot, revision) rows in the index, and verify re-running it is a no-op
- [ ] 3.5 Implement the mirror rebuild command and verify that deleting every object and thumbnail and rebuilding restores every view with unchanged content hashes
- [ ] 3.6 Verify degraded mirroring: with blob storage unreachable, ingestion commits and reports the view awaiting mirroring; with no blob storage configured at all, ingestion commits and the view is readable from the repository
- [ ] 3.7 Verify no orphan objects: a test fails ingestion before commit and asserts blob storage retains nothing from that request

## 4. Version history reads

- [ ] 4.1 Implement `list_view_revisions` over the repository's file history, newest first with identifier, person, time and content hash; verify three revisions list in order with exactly one current
- [ ] 4.2 Implement `get_view_revision` labelling any non-current revision historical, and verify an unknown identifier returns an explicit not-found naming it rather than the current image
- [ ] 4.3 Implement `compare_view_revisions` presenting the older revision first regardless of argument order, and verify the symmetric-order case, the two-historical case and the compare-with-itself case
- [ ] 4.4 Verify history is served from the repository alone: run the listing, retrieval and comparison tests with the blob store emptied
- [ ] 4.5 Implement removal of a view as a revision and verify earlier revisions stay retrievable and no revision is marked current
- [ ] 4.6 Implement truncated-history reporting and verify that a shallow working copy lists what it has and states from which point earlier revisions are unavailable

## 5. Annotations across a replacement

- [ ] 5.1 Record the authoring revision on every view-anchored annotation and verify it survives a replacement in both carried and orphaned outcomes
- [ ] 5.2 Apply the carry-forward decision on replacement and verify four annotations are all carried at an equal aspect ratio and all orphaned at a different one
- [ ] 5.3 Verify the outcome is reported: a replacement result states how many annotations were carried and how many were orphaned
- [ ] 5.4 Verify an orphaned annotation is never drawn on the new revision, and that its position on its authoring revision is still retrievable
- [ ] 5.5 Verify orphaning is not an exit: three open annotations orphaned by a replacement are still open, none recorded promoted or resolved, and all appear among the open issues of the compiled briefing
- [ ] 5.6 Implement `reanchor_annotation` as a human action recording who and when, and verify the text and open state are unchanged and that nothing re-anchors automatically across a second replacement

## 6. Freshness

- [ ] 6.1 Include the shown revision's content hash in every view reference (D8) and verify two revisions of one view present different identities
- [ ] 6.2 Implement the current-token read and the configured interval, and verify that a replaced view is reported as superseded within the interval
- [ ] 6.3 Verify the stale path: with the token unreadable, the view is marked stale and is never labelled current

## 7. Boundary enforcement and surfaces

- [ ] 7.1 Add the structural test asserting the ingestion use-case package imports neither `LLMPort` nor `VisionPort` (D12), and the behavioural test running a full ingestion with both ports wired to fakes that raise on any call
- [ ] 7.2 Verify ingestion produces no derived metadata: after ingesting a view, assert no description, tag or suggested alias exists for that asset and that its specification contains only uploaded or authored content
- [ ] 7.3 Verify the failure guarantee end to end: force a failure during the write and assert every path the request would have written is absent or byte-identical and that no commit from the request exists
- [ ] 7.4 Add the ingestion request handlers to the HTTP surface defined by `http-api` and `asset-requests`, delegating to `ingest_views` with no logic of their own; verify by the adapter structural test that the inbound module contains no conditional on image content
- [ ] 7.5 Add `canon add-view <asset> --slot <name> <file>` delegating to the same use case, so the core is exercisable against a local working copy with no server; verify the CLI and the HTTP surface produce identical commits for identical inputs
- [ ] 7.6 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check
