# Tasks

## 1. Configuration and fail-fast boot

- [x] 1.1 Implement the frozen settings model in `libs/cybercanon/adapters/wiring/settings.py` with file loading explicitly disabled (D3) and verify a test asserting that a value present only in a file on disk and in the image is not picked up
- [x] 1.2 Aggregate missing and malformed required settings into one startup error naming every offending setting and, for a malformed value, its expected shape; verify a test with two settings absent asserts both names appear in a single message
- [x] 1.3 Declare secret settings with a redacting type and verify a test that a malformed secret's failure message contains the setting name and not its value, including when the error is rendered through a traceback
- [x] 1.4 Verify optional configuration does not block boot: a test starting the API with the model switch off and no model settings present, asserting startup succeeds and the model-dependent features report unavailable
- [x] 1.5 Write `deploy/README.md` listing every required and optional variable per service, and verify a test asserting the settings model and that document name the same variables

## 2. Health, readiness and status

- [x] 2.1 Implement `ServiceHealth` and `ComponentStatus` value objects and a `describe_service_health` use case that classifies each dependency as owned or optional; verify unit tests over fakes covering owned-down, optional-down and all-up
- [x] 2.2 Implement `/healthz` performing no input or output (D2) and verify a test with every dependency fake raising on access asserts it still answers responsive within its normal response time
- [x] 2.3 Implement `/readyz` for the API checking only the index database and the blob store, and verify tests asserting ready with the model endpoint and the identity provider unreachable, and not ready — naming the component — with the index unreachable
- [x] 2.4 Implement `/readyz` for the web application as process-only and verify an integration test that it becomes ready with the API container stopped, and that a page renders an explicit unavailable state rather than an error
- [x] 2.5 Implement `WorkingCopyStatus` and `IndexFreshness` and expose them per project on `/status`; verify a test that advancing the working copy without rebuilding reports not-in-sync and names both revisions
- [x] 2.6 Record fetch attempt outcome and time separately from last successful fetch, and verify a test where several consecutive fetches fail asserts the last success time does not advance and the latest attempt is reported failed with its reason
- [x] 2.7 Require authentication on `/status` while leaving `/healthz` and `/readyz` open, and verify a test that an unauthenticated `/status` request is refused and that the open endpoints return no project information
- [x] 2.8 Implement structured JSON logging to stdout with request id, actor when present and project when present (D11), and verify a test that a request emits one parseable JSON line carrying all three

## 3. Container artifacts and promotion

- [ ] 3.1 Write the API `Dockerfile` with no environment-specific value at build time and verify a test that builds it twice from the same revision and asserts the resulting digests are equal
- [ ] 3.2 Write the web application `Dockerfile` using the server runtime adapter (D10) and verify the built image serves the application with no API reachable
- [x] 3.3 Add a build pipeline step that records the built digest against the revision, and verify a promotion check comparing the running digest in each environment against that record
- [x] 3.4 Add a repository secret scan to the merge gate and an artifact scan for the declared secret settings' values; verify both by introducing a fake credential in a throwaway branch and asserting each scan fails
- [ ] 3.5 Document and verify rollback as redeploying a previously recorded digest, by deploying revision N, then N-1, and asserting the previous version serves with no rebuild

## 4. Index migrations as a release step

- [x] 4.1 Implement the SQL migration runner over `db/migrations/NNNN_*.sql`, one transaction per file, recording applied versions in `schema_migrations` (D4); verify tests for fresh apply, idempotent re-apply and ordering
- [x] 4.2 Verify the failure path: a migration file that raises leaves the schema at the last completed version and the runner exits non-zero reporting that version
- [x] 4.3 Wire the runner as the Coolify pre-deploy command on the API application and verify an integration test that a failing migration aborts the release, no new instance serves a request, and the previous version is still serving
- [x] 4.4 Verify instances never migrate at start: a test starting two instances against an out-of-date schema asserts neither attempts a migration
- [x] 4.5 Implement the `drop → migrate → rebuild` recovery entry point (D5) and verify it restores an index that answers lookups identically, with no database backup involved

## 5. Persistent state and the working copy

- [x] 5.1 Provision volumes for the index database, the blob store and the per-project working copies, and verify an integration test that redeploying a new artifact preserves the indexed revision, the working-copy revision and a stored blob reference
- [x] 5.2 Implement `GitSpecStore` over the persistent working copy with clone-on-missing and fetch-and-reset to the configured branch (D6); verify tests for first clone, fetch advancing the revision, and reset discarding a local modification
- [x] 5.3 Implement the `sync_project` use case driven by both the schedule and the webhook endpoint, and verify a test that both paths update `WorkingCopyStatus` identically
- [x] 5.4 Implement the exclusive per-project lock on the working-copy volume and verify a test that two concurrent write-backs for one project are applied one after the other, each producing its own commit with neither change lost
- [x] 5.5 Implement write-back as commit-then-push with reset-on-failure, and verify a test that a push failure leaves no uncommitted modification and returns a failure stating no change was recorded
- [x] 5.6 Verify attribution end to end: a write-back by a person mapped in `.canon/actors.yaml` produces a commit authored as that person, and an unmappable actor is refused rather than committed anonymously
- [x] 5.7 Implement the index rebuild from a working copy as a resumable operation reporting progress, and verify `/status` reports a rebuild in progress and that reads not servable from the partial index report unavailability rather than an incomplete answer

## 6. Zero-downtime rollover and interrupted write-back

- [x] 6.1 Configure readiness-gated rollover with a drain window longer than the write-back timeout (D7) and verify the two configured values are asserted in that order by a test, not just documented
- [x] 6.2 Verify continuous availability: an integration test issuing reads throughout a deploy asserts every request received a response and none failed because of the rollover
- [x] 6.3 Verify a never-ready new version does not replace the old one — deploy an artifact whose readiness never reports ready and assert the previous version is still serving after the deploy times out
- [x] 6.4 Verify a write-back accepted just before retirement commits inside the drain window and returns success with the commit present on the configured branch
- [x] 6.5 Verify the abandoned case: terminate an instance mid-write-back and assert the working copy has no uncommitted modification once the service is running again and the file matches the configured branch
- [x] 6.6 Verify the two-instance overlap holds the single-writer guarantee, by driving write-backs against both instances during a rollover and asserting the lock serialised them

## 7. Recovery procedures and drills

- [x] 7.1 Write `deploy/recovery.md` with the three procedures — index rebuild, blob re-mirror, working-copy re-clone — each with a stated expected duration, and verify no procedure references a backup or a restore
- [x] 7.2 Verify index recovery: destroy the pre-production index volume, run the procedure and assert lookups return the results recorded before the loss, with the elapsed time measured
- [x] 7.3 Verify blob recovery: destroy the blob volume, run the procedure and assert every repository-derived blob is retrievable again by the same reference
- [x] 7.4 Verify working-copy recovery: destroy a working-copy volume, run the procedure and assert the copy is restored at the configured branch's current revision and that the index and blob recoveries run from it
- [x] 7.5 Implement the scheduled drill job that runs all three against pre-production and appends date, procedure and measured duration to `deploy/recovery.md` (D9); verify the appended record after one scheduled run
- [x] 7.6 Add the staleness check that fails when a drill is older than its stated interval or its duration exceeded the stated expectation, and verify both failure cases with a fabricated record

## 8. Environment wiring and acceptance

- [x] 8.1 Create the four Coolify applications with their hosts, volumes, environment and health configuration (D1), and verify each component restarts individually with the other three still serving
- [ ] 8.2 Point the model endpoint at the on-prem gateway from inside the deployment network and verify a test that concept images are described without egress to a third-party endpoint
- [x] 8.3 Configure the identity provider adapter's key cache with a TTL (D8) and verify a test that existing tokens still verify while the provider is unreachable and that `/status` names it unreachable
- [ ] 8.4 Stand up pre-production from the same artifacts following the Migration Plan order, and verify each numbered step's stated confirmation
- [x] 8.5 Verify the un-hosted inventory: a check asserting the deployed component set is exactly the four specified, and a test asserting the agent server listens on no network port
- [x] 8.6 Verify local-first independence: with every hosted component stopped, run a validation and an agent lookup on a developer machine and assert both complete normally
- [x] 8.7 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check, and confirm every function added here is within the backend target of 15
