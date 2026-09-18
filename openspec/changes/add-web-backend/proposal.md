# Proposal

## Why

Changes 1–3 are deliberately machine-local: the `canon` binary and the stdio MCP
server run against the developer's own working copy, need no identity and deploy
nowhere. That ordering bought adoption without asking an artist to change a habit,
and it has run out. Every remaining thing this product exists for — a model sheet
an art director can pin, a 3D viewer a modeller can spin, an annotation someone
promotes into a rule — is a *shared* surface, and a shared surface needs a server
that several people reach, an identity that says which person is acting, and a way
for that server to read and write a git repository it does not own.

This change is **roadmap position 4a: the first deployed surface**, and it is the
prerequisite for every artist-facing change that follows. It comes now because the
schema has already proven itself locally, so the server is a way to reach a
contract that exists rather than a bet on one that might.

It also **closes the open tension recorded in `project.md`**. That document leaves
"how the hosted API reaches the git repository" unresolved and says it must be
settled before the web surface is specified. It is settled here: a **persistent
working copy per project**, refreshed on a schedule and on webhook, with write-back
as a **direct commit to a configured branch**, attributed to the acting person
through `.canon/actors.yaml`. Not a pull request — a pull request per accepted
alias or promoted rule would make the review queue the bottleneck for edits whose
review already happened in the tool.

The failure this change must not introduce is the one the whole product exists to
prevent: a second implementation. A "Validate" button that disagrees with
`canon validate` destroys the trust the validator was built to create, so the HTTP
surface holds no validation, compilation or lookup logic of its own.

## What Changes

- **A FastAPI surface that is a thin adapter** — it maps requests to the *same*
  use cases the CLI and the MCP server call, renders their results, and contains
  no rule, no compiler and no lookup of its own.
- **Deterministic error mapping** — domain outcomes translate to status codes by a
  single table. A refusal the domain expressed is never an internal error.
- **Pagination, idempotency and versioning** as surface concerns: stable ordering
  with opaque cursors, replayable state-changing requests, and an explicit API
  version whose additive evolution does not break a deployed client.
- **CyberdyneAuth integration** — OIDC authorization-code with PKCE for the web
  app, JWT verification against the published key set, device-code plus OS keychain
  for the CLI, client-credentials for background work. **Identity and tenant come
  only from verified claims**, never from a path segment or a request body.
- **Claims translate, they do not decide.** The adapter turns groups and claims
  into a domain `Actor` with `Role`s; every authorization decision stays domain
  policy, verifiable with no identity service running.
- **The persistent working copy** — cloned per project, fetched on a schedule and
  on webhook, serving reads from a consistent revision that is never a
  half-finished fetch, with the **staleness window surfaced on every read** rather
  than hidden.
- **Direct-commit write-back** — an accepted edit becomes one commit on a
  configured branch, authored by the acting person via the actors mapping,
  refused outright when that person cannot be mapped to a git identity.
- **Conflict handling that never overwrites** — an edit carries the revision it was
  based on; a file changed underneath it produces a conflict with the current
  state, not a silent clobber.
- **PostgreSQL stays a rebuildable index.** Dropping it and rebuilding from the
  working copy SHALL restore every answer the surface gives. Nothing is stored only
  there.
- **MinIO is a blob mirror** — content-addressed keys for views, exports and
  preview meshes, re-mirrorable after total loss, read through signed time-limited
  URLs.
- **Asset requests** — a developer asking a person for an asset that exists or does
  not exist yet, assigned by discipline, with its own lifecycle that *observes* the
  asset status lifecycle and never drives it. Notification is in-app and minimal.

## Capabilities

### New Capabilities

- `http-api`: the HTTP surface — resource shape, the domain-outcome-to-status-code
  mapping, pagination, idempotency, versioning, health, and the enforced rule that
  it is a thin adapter over the same use cases the other surfaces call.
- `auth-integration`: identity and tenancy from verified claims only — token
  verification, the claims-to-`Actor` translation boundary, group-to-role mapping,
  the three credential flows (interactive, device, service), and bounded offline
  degradation.
- `hosted-repository`: the persistent working copy per project — provisioning,
  scheduled and webhook refresh, surfaced staleness, read isolation from an
  in-progress fetch, direct-commit write-back with per-person attribution,
  conflict handling, and recovery from a lost or diverged working copy.
- `blob-storage`: the blob mirror for views, exports and preview meshes —
  content-addressed keys, the mirror-not-master rule, re-mirroring after loss, and
  signed time-limited read access.
- `asset-requests`: a developer asking a person for an asset — raising a request
  against an existing or not-yet-existing asset, assignment by discipline, the
  request lifecycle, its relationship to the asset status lifecycle, and minimal
  in-app notification.

### Modified Capabilities

None. No earlier change is archived yet, so a delta against an unarchived
capability cannot be written; requirements that touch `asset-lookup`,
`asset-validation`, `spec-compilation` or `canon-cli` are stated inside the
capabilities above, as constraints on this surface rather than edits to theirs.

## Non-goals

Explicitly **not** in this change:

- **No user interface.** No SvelteKit application, no asset browser, no spec
  editor, no model sheet, no viewer, no pin. This change ends at the HTTP contract.
- **No annotation model.** Creating, anchoring, triaging and promoting annotations
  belong to `add-model-sheet-2d`. This surface carries the rule that promotion is a
  human action; it does not define what an annotation is.
- **No 3D anchoring, re-projection or orphan detection.** That is `add-viewer-3d`.
- **No MCP write tools.** `add-mcp-writes` decides those; nothing here expands the
  agent surface, and promotion remains not agent-callable.
- **No hosted MCP mode.** The MCP server stays stdio and local-first; this change
  does not give it a port, a CORS policy or a network threat model.
- **No deployment specification.** Containers, health-check wiring, migration
  release steps, volumes and Coolify configuration are `add-coolify-deployment`.
  This change states *that* a health endpoint exists and what it must not depend
  on, not how it is deployed.
- **No pull-request workflow, no branch-per-edit, no review queue.** Write-back is
  a direct commit by decision, and the alternative is recorded in `design.md`.
- **No CyberArche integration.** Linking long-form documents and delegating
  semantic search are `add-cyberarche-integration`.
- **No embeddings, no vector search.** The index stays exact and full-text.
- **No email or push notification, no digest, no subscription preferences.**
  Request notification is in-app and visible to the assignee, and nothing more.
- **No multi-repository projects, no monorepo sub-path composition.** One project
  maps to one repository and one configured branch.
- **No web-based git operations.** No branching, merging, history browsing or
  conflict resolution UI; the repository's own tooling keeps that job.

## Impact

- **New code** — `libs/cybercanon/application/ports/` gains `repository_host`,
  `clock` and `notifier`; new use cases `raise_request`, `assign_request`,
  `transition_request`, `refresh_project`, `rebuild_index`; domain additions for
  `Tenant`, `Role` mapping policy, `AssetRequest` and its transitions;
  `libs/cybercanon/adapters/outbound/{postgres,minio,auth}`;
  `libs/cybercanon/adapters/inbound/http`; `services/cybercanon/api`;
  `db/migrations/`.
- **New dependencies** — `fastapi`, `uvicorn`, an async PostgreSQL driver and
  migration runner, an S3 client, a JWT/JWKS verification library, and `httpx` for
  outbound calls. No identity SDK reaches beyond the auth adapter.
- **Configuration** — repository URL, branch and credentials per project; fetch
  interval and webhook secret; CyberdyneAuth issuer, audience, key set URL and the
  group-to-role mapping; PostgreSQL and S3 connection settings. All environment
  variables with no file fallback, per `project.md`.
- **Consumer-side impact** — a game repository adopting the hosted surface gains
  `.canon/actors.yaml` mapping verified subjects to git identities, a webhook
  pointed at the API, and commits on the configured branch authored by the people
  who made the edits in the tool.
- **Resolved in `project.md`** — the "open tension" section on how a hosted API
  reaches git is answered by `hosted-repository`; `project.md` should be updated to
  record the decision and move roadmap item 7's git-access question here.
