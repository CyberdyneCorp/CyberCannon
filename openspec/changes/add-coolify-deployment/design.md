# Design

## Context

Changes 1–3 deploy nothing: the CLI, the agent server and the core run against a
developer's own working copy. `add-web-backend` breaks that — it introduces an
HTTP surface, an index, a blob mirror and, unavoidably, a **hosted process that
must read a git repository it does not own**. That was the open tension in
`openspec/project.md`, and it is now settled: a **persistent working copy per
project**, fetched on a schedule and on webhook, with write-back as a **direct
commit to a configured branch**, attributed through `.canon/actors.yaml`.

This change describes how that runs on the Cyberdyne Coolify instance at
`https://coolify.cyberdynecorp.ai`, under the shared
`<service>.backend.coolify.cyberdynecorp.ai` convention, alongside CyberdyneAuth,
CyberdyneRAG and the DAO backend.

Two project-level constraints do most of the work below. **Git is the source of
truth**, so every piece of hosted state is derived and every recovery is a
rebuild. And **the agent server is stdio and local-first**, so the deployed
inventory is smaller than it looks — which is a property to defend, not an
accident to fix later.

Ports and value objects touched: `SpecStore` (a `GitSpecStore` over a persistent
working copy rather than a developer's checkout), `SearchIndex` (PostgreSQL
replacing the local SQLite implementation from `add-mcp-read-server`, behind the
same port), `BlobStore` (MinIO), `IdentityProvider`, `LLMPort` / `VisionPort`.
New application-level value objects: `ServiceHealth`, `ComponentStatus`,
`WorkingCopyStatus` (revision, `last_fetch_at`, `last_attempt_at`,
`last_attempt_error`) and `IndexFreshness` (`indexed_revision`,
`working_copy_revision`, `in_sync`). Nothing here enters the domain: the domain
knows nothing about deployment, and it stays that way.

## Goals / Non-Goals

**Goals:**

- Make another system's outage incapable of failing a CyberCanon deploy.
- Make every piece of hosted state disposable, with a recovery whose duration is
  a measured number rather than a guess.
- Make a misconfiguration visible at boot, in one message, naming the setting.
- Keep the same artifact from staging to production, so "it worked in staging"
  means something.
- Keep the working copy single-writer without giving up zero-downtime deploys.

**Non-Goals (design level):**

- No orchestration beyond one Coolify node. Horizontal scaling changes the
  working-copy ownership decision (D6) and is a new design, not a config change.
- No metrics pipeline. The status surface answers the two questions that get
  asked; anything more is speculative instrumentation.
- No secret management beyond Coolify's environment.
- No blue/green with a duplicated database. The index is rebuildable; a second
  copy of it buys nothing a rebuild does not.

## Decisions

### D1 — Four Coolify applications, one container definition each, no compose file as the unit of deployment

Each deployed component is its own Coolify application with its own environment,
its own health configuration and its own volumes: `api.backend.…`,
`canon.backend.…` (web), plus managed PostgreSQL and MinIO. The API and web
images are built from a `Dockerfile` each, in-repo.

*Why:* Coolify restarts, rolls and configures per application; a single compose
stack makes every deploy a whole-stack deploy and hides which component actually
failed. **Alternative rejected:** one `docker-compose.yml` as the deployment unit,
which is simpler to read and would have made the requirement "a component
restarts without taking the others down" false by construction. **Cost accepted:**
four places to keep environment lists honest, mitigated by D3 — a service that is
missing a variable refuses to start and names it, so the drift surfaces on the
first deploy rather than on the first request.

### D2 — Three endpoints: `/healthz` (liveness), `/readyz` (readiness), `/status` (operational detail)

`/healthz` returns a constant and touches nothing. `/readyz` checks only the
dependencies the service owns — for the API, the index database and the blob
store; for the web application, nothing at all. `/status` reports per-dependency
state, per-project working-copy revision and fetch times, and index freshness.

*Why:* a single aggregated `/health` is exactly the cascade the spec forbids:
whatever it checks becomes a deploy blocker, and someone always adds the model
gateway to it "for visibility". Splitting visibility (`/status`) from gating
(`/readyz`) removes the temptation structurally. **Alternative rejected:** one
endpoint with a severity field per dependency and a rule about which severities
block — the rule lives in the platform's health configuration, where nobody
reviews it. **Cost accepted:** three endpoints, and `/status` needs the same
authentication as the rest of the API because it names projects; `/healthz` and
`/readyz` stay unauthenticated and say nothing but the state.

### D3 — Configuration is one frozen settings object, validated in the composition root, environment-only

A `pydantic-settings` model with file loading explicitly disabled is constructed
once in `adapters/wiring/`, before any adapter. Missing or malformed required
values raise a single aggregated error listing every offending setting; secret
fields render as a redacted type so a traceback cannot print them. Nothing below
the wiring layer reads the environment — use cases and adapters receive values.

*Why:* the spec requires both environment-only configuration and a boot that fails
naming what is missing. One construction point makes both true at once, and makes
"which variables does this service need?" answerable by reading one file.
**Alternative rejected:** per-adapter `os.environ` reads, which are convenient and
guarantee that half the missing variables are discovered one request at a time.
**Cost accepted:** a dependency (`pydantic-settings`) and the discipline that new
configuration is added in one place.

### D4 — Migrations are a release command running the same image, applying numbered SQL files inside a transaction

Coolify runs a pre-deploy command on the API image: a small runner that applies
`db/migrations/NNNN_*.sql` in order, each file in a single transaction, recording
applied versions in a `schema_migrations` table. A non-zero exit aborts the
release; the previous version keeps serving. Instances never migrate at start.

*Why:* migrate-on-boot races N instances against each other and couples schema
change to a health check. Running the same image guarantees the runner and the
code agree about the target version. PostgreSQL's transactional DDL means a failed
file leaves the schema at the last completed version — the "defined state" the
spec demands. **Alternative rejected:** Alembic, which is the standard answer and
assumes a model layer the index does not have; plain SQL files stay readable by
anyone who can read the queries. **Cost accepted:** no automatic downgrade path.

### D5 — There are no index backups, deliberately, and recovery is `drop → migrate → rebuild`

The documented recovery for a broken schema or a lost volume is: drop the
database, apply migrations to the target version, and rebuild every project's
index from its working copy. The blob equivalent re-derives blobs from the working
copy.

*Why:* a restore path would make the index authoritative in practice even while
`project.md` says it is not — the first time a restore is chosen over a rebuild,
the rebuild path rots and the claim becomes false. **Alternative rejected:**
nightly `pg_dump` "just in case", which costs almost nothing to run and everything
to the architecture. **Cost accepted:** recovery time scales with asset count
rather than being constant; D9 makes that number measured and watched, and the
day it stops being acceptable is the day the index stops being a cache.

### D6 — The working copy is a volume owned by the API application, with writes serialised by a per-project lock on that volume

One volume per project under `/data/worktrees/<project>`, mounted by the API
application. A scheduled fetch and a webhook endpoint both drive the same
`sync_project` use case. Write-back takes an exclusive per-project file lock on
the volume, commits, pushes, and releases; on any failure the working copy is
reset to `origin/<branch>` and the caller is told the write failed.

*Why:* the alternative for git access — reading through the git host's API — was
rejected: it rate-limits, it cannot give an atomic multi-file read at one
revision, and it makes every spec read depend on a third party being up, which is
the cascade this change exists to prevent. A lock on the volume rather than in
process memory is what makes D7's overlapping instances safe. **Alternative
rejected:** a dedicated single-instance sync worker owning the volume, which is
cleaner and adds a fifth deployed component — rejected to keep the hosted
inventory at four, and revisited the moment the API needs a second node.
**Cost accepted:** the API is pinned to the node holding the volumes; horizontal
scaling across nodes is out of reach until this decision is revisited.

### D7 — Rollover overlaps instances; the drain window is longer than the write-back budget

Coolify starts the new instance, waits for `/readyz`, routes to it, then signals
the old one, which stops accepting requests and drains. The drain window is
configured longer than the write-back timeout, so an accepted write-back either
finishes inside the window or is abandoned by the timeout before termination.

*Why:* it makes "a commit or nothing" a property of two configured numbers in a
known order rather than a hope about process shutdown. During the overlap both
instances hold the same volume, and D6's lock — not instance count — is what keeps
a project single-writer. **Alternative rejected:** refusing writes during a deploy
(a maintenance flag), which is simpler and turns every deploy into a visible
outage for the one operation users care most about. **Cost accepted:** a deploy
takes as long as the drain window in the worst case.

### D8 — The identity provider's keys are cached, so an auth outage costs new sessions and nothing else

The `IdentityProvider` adapter caches the signing keys with a TTL and continues
verifying existing tokens while the provider is unreachable. Readiness never
consults it; `/status` reports it unreachable.

*Why:* the spec requires readiness to survive an identity outage, but the honest
consequence had to be stated somewhere: verification keeps working, new logins do
not. **Alternative rejected:** failing reads closed when the provider is down,
which is more conservative and converts a login outage into a total outage.
**Cost accepted:** a bounded window where a key rotated during an outage is not
yet known, ending at the TTL.

### D9 — Recovery drills run as a scheduled job against the pre-production environment and write their own record

A scheduled job destroys a pre-production volume, runs the documented procedure,
measures the elapsed time and appends date, procedure and duration to
`deploy/recovery.md`. A drill older than its stated interval is a failing check.

*Why:* `project.md` says the recovery "must be a documented, tested operation, not
a hope"; a procedure nobody has executed since it was written is a hope with
formatting. Having the drill write the record removes the step humans skip.
**Alternative rejected:** a manual quarterly exercise with a calendar reminder.
**Cost accepted:** a pre-production environment that must stay close enough to
production for the measured duration to mean anything.

### D10 — The web application runs with a server runtime, and renders a degraded shell when the API is unreachable

The SvelteKit application is deployed with a node adapter. Its readiness is
process-only: it never calls the API to decide whether it is ready, and a page
whose data cannot be fetched renders an explicit unavailable state.

*Why:* the spec forbids the web application's readiness from depending on the API.
A static build would make that trivially true, but server-side rendering of
authenticated pages and the auth callback both want a server. **Alternative
rejected:** the static adapter with a client-only shell. **Cost accepted:** a Node
runtime to operate and patch, and the discipline that no top-level load function
may throw when the API is down.

### D11 — Logs are structured JSON on stdout, and that is the whole logging design

Every service logs JSON lines to stdout with a request id, the acting actor when
there is one, and the project when there is one. Coolify collects them. Nothing
ships logs anywhere else.

*Why:* the operational questions in the spec are answered by `/status`, not by log
search; logs are for after the fact. **Alternative rejected:** an aggregation
stack, deferred until there is a second node or a second operator. **Cost
accepted:** retention is whatever the platform keeps.

## Risks / Trade-offs

- **The volume pins the API to one node** (D6) → Accepted explicitly and recorded
  here, so that the first horizontal-scaling conversation starts from "revisit D6"
  rather than from a mysterious data corruption incident. The lock is on the
  volume, so a second instance on the *same* node is already safe.
- **A slow fetch interval serves yesterday's specification as today's** → The
  webhook is the primary trigger and the schedule is the fallback; `/status`
  exposes the working-copy revision; `asset-lookup`'s existing prohibition on
  serving a stale answer as current still applies to the hosted index.
- **Rebuild duration grows silently with asset count** → D9 measures it on every
  drill and records it; a drill whose duration exceeds the stated expectation
  fails, which is the signal to change the architecture rather than the signal to
  add backups.
- **A direct commit to the configured branch lands a bad write in the studio's
  history** → The branch is configurable and may be a dedicated one; every commit
  is attributed to the acting person via `.canon/actors.yaml`; the remedy is
  `git revert`, which is available precisely because git is the source of truth.
  A pull-request flow was rejected in `project.md` — a spec edit that waits for
  review is a spec edit that does not happen.
- **Environment drift between Coolify applications** → D3 turns drift into a
  refused boot naming the variable; `deploy/README.md` lists every variable per
  service and a test asserts the settings model and that list agree.
- **A failed migration during a release with users online** → The release aborts
  before any new instance serves, so users stay on the old version; the recorded
  schema version tells the operator whether to retry or to drop and rebuild.
- **`/status` leaks project structure** → Authenticated like the rest of the API;
  `/healthz` and `/readyz` stay open and return no project information.

## Migration Plan

Greenfield: there is no existing deployment, so there is nothing to migrate from
and no cutover. Order of standing up an environment:

1. Create the PostgreSQL and MinIO applications with their volumes; record the
   connection settings as environment on the API application.
2. Create the per-project working-copy volumes and the deploy credential; run the
   initial clone; confirm `/status` reports a revision and a fetch time.
3. Run the migration release command against the empty database; confirm the
   reported schema version.
4. Deploy the API; confirm `/healthz`, `/readyz` and `/status`, including that
   `/readyz` reports ready with the model gateway and the identity provider
   deliberately misconfigured.
5. Build the index for each project; confirm `/status` reports it in sync.
6. Deploy the web application; confirm it becomes ready with the API stopped.
7. Register the git webhook; confirm a push advances the working-copy revision.

Pre-production is stood up the same way, from the same artifacts, and is the
environment D9's drills run against. Rollback of a release is deploying the
previous recorded digest; rollback of a schema is drop, migrate to the previous
version, rebuild.

## Open Questions

- **The scheduled fetch interval and the write-back timeout as concrete numbers.**
  Both are configuration; the behaviours they govern — bounded staleness, and a
  drain window longer than the write-back budget — are already specified.
- **Whether each project gets its own volume or all working copies share one.**
  Per-project volumes make recovery granular; a shared volume is easier to size.
  Either satisfies the specification, and the choice can change without one.
- **Preview blob retention.** Blobs are re-derivable, so retention is a cost
  decision rather than a durability one; it can be answered once real volumes
  exist.
