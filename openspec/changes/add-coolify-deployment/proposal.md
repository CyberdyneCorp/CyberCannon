# Proposal

## Why

Every change authored so far runs on a laptop. `canon validate`, the agent
server and the whole hexagonal core need no host, no port and no operator — which
is exactly why they could be specified first. The moment a web surface exists,
that stops being true: `add-web-backend`, `add-concept-ingestion`,
`add-model-sheet-2d` and `add-viewer-3d` all assume a reachable HTTP API, an
index, a blob store and a working copy of the game repository that someone keeps
fetched. None of them say who runs those, what "healthy" means, or what happens
when a volume is lost.

This is **roadmap position 7**, and it comes now for two reasons. First, the
question that blocked it is settled: the hosted API reaches git through a
**persistent working copy per project**, fetched on a schedule and on webhook,
writing back as a direct commit to a configured branch. With that resolved there
is a deployable shape to describe. Second, the parallel web changes are being
written against an environment that does not exist; specifying the environment
after they ship means discovering its constraints as outages.

The expensive failure this change prevents is **a cascade**: a service whose
readiness check touches the language model gateway, the identity provider or a
sibling backend turns someone else's outage into a failed deploy of CyberCanon.
The second is **a false emergency**: PostgreSQL and MinIO hold a rebuildable
index and a blob mirror, so losing them is a rebuild, not a data-loss incident —
but only if the rebuild is a tested procedure with a known duration rather than a
sentence in `project.md`.

## What Changes

- **A defined deployed inventory** — the HTTP API service, the web application,
  the index database and the blob store are hosted on the Cyberdyne Coolify
  instance under the `<service>.backend.coolify.cyberdynecorp.ai` convention.
- **A defined *un*-deployed inventory, as a requirement rather than a note** — the
  `canon` command line and the agent server are never hosted. The agent server is
  stdio and local-first by design; hosting it would add an open port, a CORS
  surface and a network threat model that local-first exists to avoid.
- **Configuration from the environment only**, with no file fallback, no secret in
  the repository, and no configuration baked into an image.
- **One image, promoted unchanged** — the artifact that passed staging is the
  artifact that runs in production, byte for byte.
- **Fail-fast boot** — a service with missing or malformed required configuration
  refuses to start and names what is missing, instead of serving a surface whose
  first real request discovers the problem.
- **Liveness separated from readiness**, and readiness that depends only on what
  the service itself owns. A model gateway, an identity provider or a sibling
  backend being unreachable degrades a feature and is reported as degraded; it
  never makes a deploy fail.
- **Migrations as a release step** with a defined failure state, and recovery by
  **rebuilding the index** rather than restoring a backup — which is only coherent
  because the index is not a source of truth.
- **Persistent volumes** for the index, the blob mirror and the per-project
  working copies, each with a **documented, tested, duration-stated recovery**:
  the index rebuilds from the working copy, blobs re-mirror from it, the working
  copy re-clones from the git host.
- **Operational visibility for the two questions that actually get asked** — "is
  the index stale?" and "when did the working copy last fetch?" — answerable
  without shell access to a container.
- **Zero-downtime rollover**, and a stated outcome for a write-back commit that is
  in flight when an instance is replaced: it either lands as a commit on the
  configured branch or leaves nothing at all, and the caller is told which.

## Capabilities

### New Capabilities

- `deployment-operations`: what is hosted and what deliberately is not, how a
  deployed service is configured and how it refuses to start when it is not,
  liveness versus readiness and which dependencies may influence each, migrations
  as a release step, persistent state and its tested recovery paths, operational
  visibility of index and working-copy freshness, and the behaviour of a deploy
  and of an in-flight write-back during rollover.

### Modified Capabilities

None. No earlier change is archived yet, so a delta against an unarchived
capability cannot be written. Requirements that touch `http-api`,
`hosted-repository`, `blob-storage` and `llm-integration` are stated here as
deployment-time behaviour of `deployment-operations` instead.

## Non-goals

Explicitly **not** in this change:

- **No multi-node orchestration.** No Kubernetes, no autoscaling, no horizontal
  replication of the service that owns a working copy. One Coolify node.
- **No hosted agent server, in any mode.** Not behind authentication, not on an
  internal network, not "temporarily for a demo".
- **No backup-and-restore product for the index or the blob mirror.** Recovery is
  rebuild and re-mirror. Specifying a restore path would quietly promote the
  database to a source of truth.
- **No disaster recovery for git itself.** The game repository's durability is the
  git host's responsibility; CyberCanon's working copy is a cache of it.
- **No metrics, tracing or alerting stack.** Structured logs and a status surface,
  not Prometheus, Grafana or an on-call rotation.
- **No secret-manager integration.** Coolify's environment is where secrets live
  in this change.
- **No operation of sibling services.** CyberdyneAuth, CyberArche and the on-prem
  model gateway are consumed, never deployed here.
- **No multi-tenant hosting.** One Coolify project serving one studio's projects.
- **No capacity planning or load testing.** Recovery durations are measured;
  throughput targets are not set.
- **No pull-request-based write-back.** Settled: direct commit to a configured
  branch.

## Impact

- **New code** — a settings module in `libs/cybercanon/adapters/wiring/`
  validating required environment at construction; a `describe_service_health`
  use case in `libs/cybercanon/application/use_cases/` returning a
  `ServiceHealth` value object; health, readiness and status routes in
  `libs/cybercanon/adapters/inbound/http/`; a SQL migration runner over
  `db/migrations/`; an index rebuild entry point reusing the same use case the
  scheduled sync uses.
- **New artifacts** — one container definition per deployed service, a Coolify
  application definition per service with its declared environment, a
  `deploy/README.md` naming every required variable, and `deploy/recovery.md`
  holding the three drilled recovery procedures with their measured durations.
- **New dependencies** — `pydantic-settings` for environment-only configuration.
  The migration runner is plain SQL over `psycopg`, deliberately adding nothing.
- **Operational impact** — the game repository needs a read/write deploy
  credential and a webhook pointing at the API; the studio needs a git identity
  for the service and a `.canon/actors.yaml` mapping so write-backs are attributed
  to the acting person rather than to a robot.
- **Change ordering** — this change describes how `add-web-backend` is run. It
  must land with or after it; nothing here is useful while there is no HTTP
  surface to host.
