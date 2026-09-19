# Tasks

## 1. Service skeleton and the layering contract for a third adapter

- [x] 1.1 Create `services/cybercanon/api` and `libs/cybercanon/adapters/inbound/http`, and verify `uvicorn` serves the health endpoint on a clean checkout with no database, no identity service and no repository configured
- [x] 1.2 Extend the `import-linter` contracts to cover the HTTP adapter (`adapters/inbound/http` must not import `adapters/outbound`) and verify `lint-imports` fails on a deliberate violating import and passes once removed
- [x] 1.3 Add the structural test asserting the HTTP adapter contains no conditional on specification content and no rule, budget or naming logic (mirrors the MCP adapter's test); verify it fails when such a conditional is introduced
- [x] 1.4 Add the environment-variable configuration model with no file fallback (repository, branch, credential, fetch interval, webhook secret, issuer, audience, key set URL, group mapping, database, object store, link expiry) and verify the service refuses to start naming every missing required variable at once

## 2. Domain — tenancy, roles, authorization policy

- [x] 2.1 Model `Tenant`, extend `Actor` with a tenant and a stable subject identifier, and verify a request for a project outside the actor's tenant is refused by policy alone
- [x] 2.2 Implement the authorization policy as pure functions over `(Actor, operation, subject)` and verify the full policy suite runs with no identity service, no HTTP and no database
- [x] 2.3 Implement the human-only operation registry in the domain and verify a test enumerates every mutating operation and asserts each declares whether it requires a person (D13)
- [x] 2.4 Verify promotion of an annotation to a durable rule and acceptance of a derived suggestion are both registered as human-only, and that an actor authenticated as automation holding every role is refused each

## 3. Domain — asset requests

- [x] 3.1 Model `Discipline`, `AssetRequest` (author, discipline, description, optional asset reference, optional asked-for status, assignee, state, history) and verify a request with no description is rejected
- [x] 3.2 Implement `RequestState` and the transition table (`open→accepted|declined|withdrawn`, `accepted→fulfilled|declined|withdrawn`, three terminal states) as a pure function and verify every disallowed transition is refused, including `fulfilled→open`
- [x] 3.3 Implement the decline-requires-reason and author-only-withdraw rules and verify each with a failing case
- [x] 3.4 Implement assignment resolution (asset discipline owner → project discipline owner → unassigned) as a pure function and verify all three outcomes, and that the author is never the fallback assignee
- [x] 3.5 Implement the fulfilment precondition against the asked-for asset status and verify fulfilment is refused naming the current status, then succeeds once the asset reaches it
- [x] 3.6 Verify by test that no request transition function returns a changed asset status and that no asset status transition returns a changed request state

## 4. Application — outcome vocabulary, ports and use cases

- [x] 4.1 Introduce the result union (`Ok`, `NotFound`, `Forbidden`, `Unauthenticated`, `Invalid`, `Conflict`, `Unavailable`) with stable error identifiers (D10) and verify a test asserts every member is constructible with a subject and an identifier
- [x] 4.2 Migrate the existing use cases from raising to returning the union, update the CLI and MCP adapters, and verify the whole existing test suite passes and `canon` exit codes are unchanged
- [x] 4.3 Define the `RepositoryHost` port (clone, fetch, resolve revision, read at revision, commit as author, push, recover) with an in-memory fake under `application/testing/` and verify a port-conformance suite runs against the fake
- [x] 4.4 Extend `SpecStore` with revision-pinned reads (D3) and verify the conformance suite passes for both the local path-reading and the revision-reading implementations
- [x] 4.5 Extend `BlobStore` with content-addressed put, existence check and link issuance, add an in-memory fake, and verify conformance
- [x] 4.6 Define the `Notifier` port and its fake, and verify a notification failure never changes a use case's outcome
- [x] 4.7 Implement `refresh_project` (fetch, advance the served revision atomically, record the confirmation time) and verify a failed fetch leaves the served revision unchanged and the project available
- [x] 4.8 Implement `write_back` (precondition check by content hash, commit as the mapped author, push, bounded retry per D6) and verify: clean apply, stale-hash conflict, push-rejection retry that succeeds, and retry exhaustion reported as a conflict
- [x] 4.9 Implement `raise_request`, `assign_request` and `transition_request` over `RepositoryHost` and verify each produces exactly one commit and records its actor
- [x] 4.10 Implement `rebuild_index` over the working copy and verify it is never invoked from a read path

## 5. Adapters — the hosted working copy

- [x] 5.1 Implement `GitRepositoryHost` cloning per project onto a persistent path, with provisioning, ready, unavailable and recovering states; verify a project reports provisioning rather than an empty asset list while cloning
- [x] 5.2 Implement revision-pinned reads from the git object database (D3) and verify a read issued before a fetch and completed after it returns content from the pre-fetch revision
- [x] 5.3 Implement the per-project scheduled fetch and verify a commit pushed to the remote is visible after the configured interval with no webhook involved
- [x] 5.4 Implement the webhook endpoint with origin authentication and verify: authenticated notification refreshes, unauthenticated notification is ignored with no refresh, unknown project and uninteresting branch are accepted and discarded without error
- [x] 5.5 Surface the served revision and last-confirmed time on every specification read, and verify a read after a refresh outage longer than the interval is marked as possibly stale
- [x] 5.6 Implement the actors-mapping lookup from `.canon/actors.yaml` (D8) and verify a mapped person's edit is authored by their git identity and an unmapped person's edit is refused naming the missing mapping with no commit created
- [x] 5.7 Implement single-writer serialisation per project and verify two concurrent edits to different files both apply, while two concurrent edits to the same file produce one success and one conflict
- [x] 5.8 Implement recovery by re-obtaining the working copy and verify: a deleted working copy restores and serves every specification; a diverged working copy resets to the remote and reports the discarded local commits
- [x] 5.9 Verify the failed-push path leaves no local-only commit: after a push failure the working copy matches the remote and the caller was told the edit did not apply
- [x] 5.10 Verify by test that no repository credential, path or remote URL appears in any error response body

## 6. Adapters — PostgreSQL as the rebuildable index

- [x] 6.1 Implement `PostgresSearchIndex` behind the existing `SearchIndex` port and verify the ranking cascade returns byte-identical results to the local implementation for the same fixture project
- [x] 6.2 Add the migration set and a migration runner invoked as a release step, and verify a migration applied to an empty database yields a schema the rebuild populates without manual intervention
- [x] 6.3 Implement the full rebuild from the working copy and verify the drop-and-rebuild guarantee: record the results of every lookup, listing, search and read for a fixture project, drop the database, rebuild, and assert every result is identical
- [x] 6.4 Verify no durable content reaches only the index: a test enumerates every write use case and asserts each produces a repository commit
- [x] 6.5 Implement idempotency-key storage with a bounded lifetime (D11) and verify replay returns the original outcome, a differing body with the same key is refused, and a retried write produces exactly one commit

## 7. Adapters — the blob mirror

- [x] 7.1 Implement `S3BlobStore` with content-digest keys and verify identical content from two assets stores once under one key, and that a rename with unchanged content keeps the key
- [x] 7.2 Implement idempotent mirroring and atomic visibility, and verify an interrupted upload leaves nothing readable at its key
- [x] 7.3 Implement the re-mirror operation from the working copy and verify that emptying the store and re-mirroring restores every view, export and preview mesh under its original key
- [x] 7.4 Implement digest verification on read and verify a deliberately corrupted object is reported as corrupt rather than served, and is repaired by re-mirroring
- [x] 7.5 Implement signed time-limited single-object link issuance after the authorization decision, and verify: an expired link is refused, a link rewritten to another object is refused, and no link is issued to an actor who may not read the asset
- [x] 7.6 Verify a blob with no repository-side source is refused, and that a view removed from the repository stops being listed even while its object remains stored

## 8. Adapters — CyberdyneAuth

- [x] 8.1 Implement credential verification against the issuer's published keys with issuer, audience and validity checks, and verify expired, wrong-audience and unverifiable credentials are each refused as unauthenticated
- [x] 8.2 Implement key-set caching with refresh on unknown key identifier, and verify a credential signed by a newly published key is accepted without restarting or reconfiguring the service
- [x] 8.3 Implement the configured group-to-role mapping and verify an unmapped group grants no role, an all-unmapped credential resolves to a role-less actor rather than a refusal, and adding a mapping in configuration alone changes the resolved roles
- [x] 8.4 Verify the credential representation never escapes the adapter: a test asserts recorded actions and authorization decisions contain no claim or group name, and that the policy suite runs with the adapter absent
- [x] 8.5 Implement bounded offline degradation and verify: a valid unexpired credential is served from cached keys while the issuer is unreachable, a missing credential is refused rather than served anonymously, and requests past the configured window are refused naming the identity service
- [x] 8.6 Implement the device-authorization sign-in for the CLI with operating-system keychain storage, and verify the working tree is unchanged after sign-in, no credential exists in any file under the repository, and sign-out removes it
- [x] 8.7 Verify `canon validate` still completes on a machine that has never signed in and with every network call configured to fail
- [x] 8.8 Implement service-credential authentication for background work and verify scheduled refreshes are recorded as automation naming no person, and that a supplied person identifier has no effect

## 9. Adapters — the HTTP surface

- [x] 9.1 Implement the versioned surface prefix and verify a request with no identifiable version is rejected as invalid rather than served by a default
- [x] 9.2 Implement the single outcome-to-status mapping (D10) and verify an exhaustiveness test covering every member of the result union, plus a test asserting no router catches an exception or constructs a status code directly
- [x] 9.3 Implement the error body shape (stable identifier, message, subject) and verify two endpoints producing the same outcome return the same status class and body shape
- [x] 9.4 Implement generic failure reporting with a correlation identifier and verify no response body contains a stack trace, file system path, connection string or configuration value when an outbound dependency raises
- [x] 9.5 Implement the read endpoints for assets, specifications, compiled briefings, validation and lookup, each delegating to the existing use case; verify each endpoint's handler contains no branch on specification content
- [x] 9.6 Implement pagination with deterministic ordering, a default and maximum page size, and opaque continuation tokens; verify full traversal of an unchanged data set returns each result exactly once, an oversized page request is bounded, and a token presented by an unauthorised actor is refused
- [x] 9.7 Implement the revision precondition on specification-modifying requests and verify a stale write is refused with the current revision and unchanged content, and that an omitted revision is rejected as invalid
- [x] 9.8 Wire the human-only registry into the surface and verify a service credential holding every role is refused promotion of an annotation and acceptance of a suggestion
- [x] 9.9 Implement the health report and verify it succeeds while the language model endpoint, the document platform and the identity service are all unreachable, and describes each as unavailable
- [x] 9.10 Publish the generated interface description and verify it is produced from the implemented endpoints rather than maintained by hand

## 10. Requests and notification end to end

- [x] 10.1 Implement the request endpoints (raise, assign, transition, list, read) and verify a reader-only actor may raise while a non-assignee without the responsible role is refused acceptance, naming the required role
- [x] 10.2 Implement request persistence as one repository file per request (D7) and verify a full lifecycle produces one commit per transition, each authored by the acting person
- [x] 10.3 Verify the index-rebuild guarantee for requests: create open, accepted and terminal requests, drop and rebuild the index, and assert state, assignee and attribution are unchanged
- [x] 10.4 Verify a request whose persistence fails does not appear in the listing and that its author is told it was not recorded
- [x] 10.5 Implement unread items as a derived query plus a per-person dismissal flag (D9) and verify the assignee sees the request, one person's dismissal leaves it unread for the other, and a failing notifier does not reverse an acceptance
- [x] 10.6 Verify no request operation creates or changes a constraint, a silhouette rule or any other durable specification content

## 11. Cross-surface equivalence and operational drills

- [x] 11.1 Verify one verdict across surfaces: validate the same failing export through the CLI and over HTTP and assert identical violations, severities and overall outcome
- [x] 11.2 Verify one briefing across surfaces: compile the same asset from the CLI and over HTTP at the same revision and assert byte-identical output
- [x] 11.3 Verify one lookup across surfaces: issue the same query over HTTP and through the agent surface at the same revision and assert identical assets in identical order
- [x] 11.4 Run the recovery drill end to end — delete the working copy, empty the blob store, drop the database, restart — and verify every previously answerable read, lookup, listing, request and blob is answerable again, recording the elapsed time as the documented recovery procedure
- [x] 11.5 Run the concurrency drill — two people editing the same specification and two editing different ones, with a commit pushed directly to the remote in between — and verify exactly the specified conflicts and successes
- [x] 11.6 Update `openspec/project.md` to record the resolved git-access decision, remove the open-tension section, and move the roadmap's git-access question out of item 7
- [x] 11.7 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check, and verify every function added by this change is within the backend target of 15
