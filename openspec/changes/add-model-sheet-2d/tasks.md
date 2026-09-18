# Tasks

## 1. Domain — anchors, threads, filtering, triage policy

- [ ] 1.1 Model `Anchor2D(view_name, u, v)` validating `u, v ∈ [0, 1]` at construction, alongside the existing 3D anchor, as a discriminated `Anchor` (D3); verify out-of-range and non-finite coordinates are refused at construction and that `lint-imports` still reports zero third-party imports in the domain
- [ ] 1.2 Model `Annotation` (id, kind, text, state, anchor, attribution, created/edited times), `Reply` and the ordered thread; verify a reply cannot be constructed with an anchor, a kind or a state of its own
- [ ] 1.3 Implement the authoring policy — who may create, reply, edit, delete and re-anchor — as pure functions; verify editing another person's text, deleting a thread that has replies, and creating without write access are each refused
- [ ] 1.4 Implement `AnnotationFilter` (kind set, open/resolved, orphan) and its application as a pure function; verify combined filters and that filtering never mutates the annotations it filters
- [ ] 1.5 Implement the triage policy — only an art director promotes; author, discipline owner or art director resolves; a promoted annotation cannot be reopened — as pure functions; verify every role in turn against every exit
- [ ] 1.6 Implement `PromotionTarget` (`constraints` | `concept.silhouette_rules`) and the rule-writing operation as a pure transformation over a parsed specification; verify the transformation both adds the rule and retires the annotation, and that no path produces one without the other (D6)
- [ ] 1.7 Implement `TriageEntry` and the queue ordering — same-kind count on the asset, then across the project, then reply count, then age; verify ordering is total and deterministic for entries with equal counts
- [ ] 1.8 Model `Stroke` as an ordered list of normalized points with a simplification tolerance and a per-annotation point cap (D8); verify a stroke exceeding the cap is simplified rather than truncated at the end, and that no width, colour or layer field exists on the type
- [ ] 1.9 Implement orphan detection for both anchor forms — a 2D anchor naming an absent view, a 3D anchor naming an absent part; verify an orphan is reported, remains triageable, and is never re-anchored by the system

## 2. Application — use cases and ports

- [ ] 2.1 Extend the `SpecStore` port with a read-at-revision plus attributed commit operation carrying the base revision (D5); verify the in-memory fake under `application/testing/` satisfies the same port-conformance suite as the real adapter
- [ ] 2.2 Implement `create_annotation`, `reply_to_annotation`, `edit_annotation`, `delete_annotation` and `move_annotation`; verify each writes through `SpecStore`, each refuses per the 1.3 policy, and each records attribution resolved from the credential
- [ ] 2.3 Verify attribution cannot be spoofed: a test submitting an author field, an actor id and a role parameter asserts the recorded attribution is the credential's person, and that an agent-originated write records both the person and the agent
- [ ] 2.4 Implement the base-revision conflict path — re-read, re-apply the same domain operation, commit; verify two concurrent creates on one asset both persist, and that a second conflict is reported with the submitted text returned
- [ ] 2.5 Implement idempotency on the client-generated annotation id (D5); verify a retried identical create produces exactly one annotation
- [ ] 2.6 Implement `list_annotations(asset, filter)` returning both anchor forms uniformly; verify a mixed-anchor asset returns identical field sets for both forms
- [ ] 2.7 Implement `resolve_annotation` and `reopen_annotation`; verify resolution excludes the annotation from the compiled briefing, reopening restores it to the queue, and reopening a promoted annotation is refused
- [ ] 2.8 Implement `promote_annotation` as a single validated atomic operation (D6); verify a promotion producing an invalid specification is refused with the violations, and that a simulated commit failure leaves the annotation open with no partial rule
- [ ] 2.9 Verify the briefing-never-grows rule end to end: compile a briefing, create and settle twenty annotations, compile again, assert byte-identical output
- [ ] 2.10 Implement `list_triage_queue(project, filter)` from `SpecStore` with the domain ordering (D11); verify the queue is produced with every derived index deleted, and that the indexed path returns the identical result
- [ ] 2.11 Verify promotion is unreachable from automated callers: extend change 2's exact tool-set test to assert no advertised tool writes a durable rule, and assert the promote use case is refused for an automated caller acting for an art director (D7)

## 3. Adapters — repository write path and HTTP surface

- [ ] 3.1 Implement the attributed-commit `SpecStore` write over the persistent working copy from `hosted-repository`, mapping the acting person to a git author through `.canon/actors.yaml`; verify a created annotation appears in the repository history attributed to that person
- [ ] 3.2 Verify the comment-preserving YAML round trip: a test adds, replies to and resolves an annotation in a hand-authored `asset.yaml` and asserts every unrelated line is byte-identical
- [ ] 3.3 Verify commit legibility: annotation commits carry a message prefix naming the asset and annotation id, and a promotion commit shows the added rule and the retired annotation in one diff
- [ ] 3.4 Expose the annotation, triage and queue use cases through `http-api` routes with authorization resolved by `auth-integration`; verify a structural test asserts the inbound HTTP adapter contains no conditional on annotation content and imports nothing from `adapters/outbound/`
- [ ] 3.5 Verify no annotation is readable only from the index: delete the PostgreSQL projection, rebuild from the repository, and assert every annotation, reply, author, anchor and stroke is identical to before

## 4. Frontend — the shared annotation ViewModel

- [ ] 4.1 Implement `createAnnotationViewModel()` plus the module singleton, owning selection, filter, draft text, draft strokes and pending-write state (D1); verify a test imports it in an environment with no DOM and exercises every operation
- [ ] 4.2 Implement the anchor-agnostic API — the ViewModel accepts an `Anchor` and never inspects its form; verify a test asserts no branch on anchor kind exists in the ViewModel module
- [ ] 4.3 Parameterize the annotation core suite over an anchor factory and run it with a 2D factory and a 3D stub (D12); verify both parameterizations pass with an identical case list
- [ ] 4.4 Implement the query cache keyed by project, asset and revision, with optimistic insert and invalidate-on-settle (D9); verify a failed write removes the optimistic entry, preserves the draft, and that a reload matches the repository
- [ ] 4.5 Implement typed clients under `lib/api/` for annotation, triage and queue operations; verify a test asserts no `.svelte` component in the change performs a network call directly

## 5. Frontend — the 2D model sheet

- [ ] 5.1 Implement the sheet presenting an asset's views by anchor name, including the no-views state; verify the empty state still presents identity, status and existing annotations
- [ ] 5.2 Implement the coordinate transform between presentation space and normalized image space (D3); verify a round-trip test across zoom, pan, window resize, device pixel ratio and rendition scale returns the original coordinate within float tolerance
- [ ] 5.3 Implement placement refusal outside the image bounds; verify a gesture in the letterboxing creates nothing and that no coordinate is clamped to an edge
- [ ] 5.4 Implement the single Pointer Events input path with `pointerType` intent and the session pen-seen flag (D10); verify pen and mouse produce the same anchor for the same position, that touch pans once a pen has been seen, and that touch places a pin when none has
- [ ] 5.5 Implement pin rendering, selection, the selected state, and thread-to-pin navigation across views; verify two annotations within a pin width of each other remain individually selectable
- [ ] 5.6 Implement the filter bar over kind and open/resolved state with the hidden count; verify the default presentation shows open annotations of every kind and that filtering leaves the repository unchanged
- [ ] 5.7 Implement the freehand stroke layer with undo of the last stroke and discard on cancel (D8); verify strokes are recorded normalized, scale with zoom, disappear with their annotation, and that the stored view image is byte-identical after drawing
- [ ] 5.8 Implement the thread panel — root text, kind, attribution rendered as "person, via agent", replies in order, reply box, and the exits the person may take; verify promotion is absent for a non-director and that submitting it anyway is refused by the system
- [ ] 5.9 Implement the orphan list in the thread panel with its reason; verify an orphaned annotation is listed and no pin is drawn for it
- [ ] 5.10 Build the sheet on `@cyberdynecorp/svelte-ui-core`; verify no component in the change forks or reimplements a design-system primitive

## 6. Triage pass and acceptance

- [ ] 6.1 Implement the art director's triage view over `list_triage_queue` with kind, asset and owner filters, showing each entry's same-kind counts, reply count and age; verify recurring feedback orders above isolated feedback
- [ ] 6.2 Implement the promotion flow from the triage view and the thread panel — rule text, destination choice, preview of the resulting rule — and verify the destination is stated before submission
- [ ] 6.3 Verify the frontend cognitive complexity target (8–12 per function) with the cognitive-complexity skill over the change's frontend files, and the backend target (≤15) over its use cases
- [ ] 6.4 Acceptance: on a repository with one asset and three views, place a pin with a pointer and with a stylus, reply, filter, resolve one annotation and promote another; verify `canon compile` afterwards shows the promoted rule, omits the resolved annotation, and that `git log` shows one attributed commit per action
- [ ] 6.5 Acceptance: delete PostgreSQL and MinIO, rebuild from the repository, and verify the sheet presents exactly the same pins, threads and triage queue as before
