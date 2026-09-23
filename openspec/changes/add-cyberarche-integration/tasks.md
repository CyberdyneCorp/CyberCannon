# Tasks

## 1. Domain — references, states and provenance

- [x] 1.1 Model `DocumentRef` (workspace, document id, address, linked by, linked at) as a frozen value object with well-formedness rules, and verify `lint-imports` still reports zero third-party imports in the domain
- [x] 1.2 Model `DocumentState` as the closed set readable / unreachable / missing / forbidden, and `DocumentCard` (ref, title, summary, state, resolved at); verify a test asserts a forbidden card carries no title and no summary regardless of how it is constructed
- [x] 1.3 Model `ResultProvenance` (exact, semantic) and the ordering rule that exact results precede semantic ones; verify a test asserts no comparator exists that orders a semantic result against an exact one
- [x] 1.4 Implement the content-placement rule as a pure predicate (does this statement constrain art, constrain code, or is it checkable) and verify it classifies a triangle budget as specification content and a rationale paragraph as document content
- [x] 1.5 Verify the one-way boundary structurally: a test asserts no domain or use-case signature accepts a document body

## 2. Application — the document platform port

- [x] 2.1 Define the `DocumentPlatform` port with `resolve`, `create` and `search`, each taking the caller's credential as a parameter (D2); verify a port-conformance test rejects any implementation holding a credential as construction state
- [x] 2.2 Implement the in-memory fake under `application/testing/` supporting per-actor permissions, deletion, rejection and delay, and verify it passes the port-conformance suite
- [x] 2.3 Implement `NullDocumentPlatform` returning the unavailable outcome with reason `unconfigured` for every method (D4), and verify every use case behaves correctly against it with no configuration present
- [x] 2.4 Define the unavailability reason set (unconfigured, unreachable, rejected, timed out, malformed) and verify each transport failure maps to exactly one reason

## 3. Application — linking, listing and display

- [x] 3.1 Implement `link_document` writing a reference into the asset's specification through `SpecStore`, attributed to the acting person; verify the resulting file diff contains the reference and no document body
- [x] 3.2 Implement `unlink_document` and verify the reference is removed and no call is made to the document platform
- [x] 3.3 Implement project-scoped links in the project configuration and verify an asset listing shows them distinguished from asset-scoped links
- [x] 3.4 Implement `list_linked_documents` with deterministic ordering and verify two consecutive listings of an unchanged specification are identical
- [x] 3.5 Implement card resolution with the per-actor cache keyed by `(ref, actor)` (D3) and verify a second actor receives a cold resolve rather than the first actor's cached card
- [x] 3.6 Verify state reporting: tests cover unreachable, deleted and forbidden, assert the three are distinguishable, assert a forbidden link discloses nothing, and assert one broken link does not prevent the others from listing
- [x] 3.7 Verify rename propagation: a document renamed at the platform is displayed under its new title on the next view after the cache lifetime
- [x] 3.8 Implement `create_document_for_asset` in create-then-link order (D8) and verify three cases — success links the reference, a refused creation leaves the specification unchanged, and a failed link reports the created document's address
- [x] 3.9 Verify the rebuildable guarantee: delete the document-card table, rebuild the index, and assert the same links list with the same references

## 4. Application — search routing and fan-out

- [x] 4.1 Implement the routing gate (D7) as a pure function over the query and the local result set, and verify an identifier-shaped query is never delegated while a prose query with no exact hit is
- [x] 4.2 Implement `search_assets_and_docs` running the local cascade to completion before the delegated call (D5), and verify by test ordering that no local result depends on the remote call
- [x] 4.3 Implement the time budget and verify the response returns within the budget plus local search time when the platform does not answer
- [x] 4.4 Verify degradation: separate tests for unconfigured, unreachable, rejected, timed out and malformed each assert local results are returned and the reported reason is the distinguishing one
- [x] 4.5 Verify provenance grouping (D6): a response containing both kinds groups them, orders exact first, labels semantic results as approximate and names each one's source document
- [x] 4.6 Verify a semantic hit naming an asset is not presented as that asset's record or location
- [x] 4.7 Verify miss logging: a query with no exact results but two semantic results is recorded as a local miss, and no request carrying the miss leaves the machine
- [x] 4.8 Verify determinism is untouched: the existing local search suite passes unchanged with the platform configured, unconfigured and unreachable

## 5. Adapter — CyberArche outbound

- [x] 5.1 Implement `adapters/outbound/arche/` against the port, reading `CANON_ARCHE_ENABLED` (default false), `CANON_ARCHE_BASE_URL`, `CANON_ARCHE_DEFAULT_WORKSPACE` and `CANON_ARCHE_TIMEOUT_S`; verify the composition root selects the null adapter whenever configuration is absent or incomplete
- [x] 5.2 Implement bearer forwarding of the caller's own token (D2) and verify by request capture that the token sent is the caller's and that no request is made under a service credential on a person's behalf
- [x] 5.3 Verify the payload boundary: a captured delegated request contains the query text and routing scope only, and no specification, annotation or compiled content
- [x] 5.4 Verify the adapter has no ingestion path: a test enumerates its outbound operations and asserts the only write is creating an empty pre-titled document (D10)
- [x] 5.5 Map transport outcomes onto `DocumentState` and the reason set, and verify each of 401/403, 404, connection failure, timeout and malformed body maps as specified
- [x] 5.6 Verify the naming boundary: a structural test asserts no domain or application module references CyberArche by name

## 6. Specification, compilation and validation boundaries

- [x] 6.1 Extend the specification schema with structured document references alongside the plain URLs already stored in `links`, and verify existing specifications continue to lint unchanged
- [x] 6.2 Add a lint rule for malformed document references and verify it names the offending reference
- [ ] 6.3 Extend specification compilation to render links as references with resolved titles where available, and verify compilation succeeds with the platform unreachable and grows by at most the link line for a several-thousand-word document
- [x] 6.4 Verify validation isolation: an export validated with the platform reachable and again with it unreachable produces byte-identical reports, and a prose budget in a linked document produces no violation
- [x] 6.5 Verify no specification field is generated from a document: linking, displaying and compiling an asset whose document describes a socket leaves the `design` block unchanged

## 7. Surfaces, degradation and acceptance

- [x] 7.1 Expose link, unlink, list, create-and-link and combined search through the existing HTTP surface, verifying each forwards the caller's token and that a request without one receives local-only search results
- [x] 7.2 Render link lists and grouped search results in the web application, and verify the rendered output labels the two groups and marks unresolved links by state
- [x] 7.3 Show the content-placement guidance at the point a person chooses where to write a statement, and verify the guidance names both destinations
- [x] 7.4 Run the full degradation test: with no document platform configuration, exercise asset browsing, compilation, validation, local search and link listing, and assert results are identical to a configured deployment except that document features report themselves unavailable
- [x] 7.5 Run the acceptance test: a designer creates a rationale document for `mech_scout` from the asset page, a second person with no access to that workspace sees the link marked inaccessible with no title, and a natural-language question returns the passage labelled approximate above no exact match
- [x] 7.6 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check, and confirm the backend target of 15 per function holds


## Notes

**6.3 is left unchecked because its first half contradicts the frozen spec.**
The task asks to *"render links as references **with resolved titles where
available**"*. `document-platform` forbids exactly that, twice and by name:
*"A compiled specification carries the link, never the document … SHALL NOT
include any of a linked document's body, title, summary or other resolved
content"*, and *"a title or summary resolved from the document platform SHALL
live only in the rebuildable index and SHALL NOT be written into a
specification file or into the compiled briefing, in any form"*. Specs are
frozen and the spec wins, so compilation renders each link as the bare address
it was authored as and contacts nothing:

    - **Linked document**: https://…/w/<workspace>/d/<document_id>

The *second* half of 6.3 — *"verify compilation succeeds with the platform
unreachable and grows by at most the link line for a several-thousand-word
document"* — **is** implemented and verified
(`tests/bdd/steps/document-platform.py`, scenarios *Compilation is not blocked
by the platform*, *No prose is compiled in*, *Compiled output does not vary
with platform reachability*; and measured directly: the compiled briefing is
byte-identical — sha256 `526bd82f…` — with the platform reachable, and for
each of the five unavailability reasons, and with no platform wired at all).
The line is left `- [ ]` rather than claimed, because half a task is not a
task, and the half that is missing is the half nobody should implement.

**3.9's premise does not match the implementation, and the task is checked on
the stronger reading.** There is no *document-card table*: D1 keeps resolved
display data in rebuildable storage, and the rebuildable storage a card lives
in is the per-viewer
:class:`~cybercanon.application.use_cases.documents.CardCache`. So
`tests/integration/test_document_links_write_path.py` destroys **both** halves
of what is rebuildable — the cards and the search index — rebuilds the index by
re-scanning a real git repository, and asserts the same links list with the
same references, the same scopes and the same titles, with the titles resolved
again (a rename between the two listings shows through, which it could not if
anything durable held the old one).
