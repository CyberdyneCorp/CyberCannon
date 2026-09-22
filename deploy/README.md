# Deploying CyberCanon

CyberCanon runs on the Cyberdyne Coolify instance at
`https://coolify.cyberdynecorp.ai`, as **four applications** under the shared
`<service>.backend.coolify.cyberdynecorp.ai` convention (D1):

| Application | What it is | Host |
|---|---|---|
| `api` | the FastAPI HTTP surface | `api.backend.coolify.cyberdynecorp.ai` |
| `web` | the SvelteKit application, node runtime (D10) | `canon.backend.coolify.cyberdynecorp.ai` |
| `postgres` | the **rebuildable index** — never a source of truth | internal |
| `minio` | the **blob mirror** — views, exports, preview GLBs | internal |

The `canon` command line and the agent server are **deliberately not here**. The
agent server is stdio and local-first; hosting it would add an open port, a CORS
surface and a network threat model that local-first exists to avoid.

That last paragraph is a **requirement with a scenario**, not a note, so it is
declared as data rather than remembered. [`coolify.yaml`](coolify.yaml) holds
the four applications — host, volumes, environment, health configuration,
pre-deploy command — and names the two surfaces that are never hosted with the
reason each is absent:

```
just deploy-check
```

reads it against the specification and against the settings the service
actually declares. A fifth application, an application whose component is the
`canon` binary or the agent server, a host outside the convention, a liveness
probe pointed at readiness, a stateful component with no volume, a stop grace
period that is not the drain window, or a variable the manifest gives that
nothing reads — each is a non-zero exit naming what is wrong. Coolify is
configured from that file by hand: there is one node and four applications, and
a synchroniser reaching the platform's API would be a fifth thing to operate and
a credential to hold.

## Configuration is the environment, and nothing else

Every deployed service reads its configuration from environment variables only.
There is **no file fallback** — not a file in the image, not one on a mounted
volume, not a `.env` beside the process. A service that is missing a required
variable, or that has one it cannot read, **refuses to start and names every
offending variable in one message**, with the shape each malformed one was
expected to have. No value is ever quoted back, so a mistyped credential cannot
leak through a log line or a stack trace.

> **The one carve-out.** A project's own settings file *inside its working copy*
> is **repository content**, not service configuration. It is read through the
> `SpecStore`, at a revision, exactly like the specifications beside it. This
> section is about the service; that file belongs to the canon.

Changing a value is a restart, never a rebuild: the same artifact runs in every
environment (D3, and "one artifact, promoted unchanged").

### `api` — required

The service will not start without these fourteen.

| Variable | Shape | Secret | What it is |
|---|---|:--:|---|
| `CANON_REPOSITORY_URL` | a git remote the service can reach | | where the project's repository lives |
| `CANON_REPOSITORY_BRANCH` | a branch name | | the branch write-backs are committed to |
| `CANON_REPOSITORY_CREDENTIAL` | a deploy credential | ● | read/write access to that remote |
| `CANON_FETCH_INTERVAL_S` | a whole number of seconds | | how often the scheduled fetch runs |
| `CANON_WEBHOOK_SECRET` | a shared secret | ● | what the git host signs its notifications with |
| `CANON_AUTH_ISSUER` | an issuer identifier | | the CyberdyneAuth issuer this service trusts |
| `CANON_AUTH_AUDIENCE` | an audience identifier | | what this service is addressed as in a token |
| `CANON_AUTH_KEY_SET_URL` | `scheme://host/path` | | where the signing keys are published |
| `CANON_AUTH_GROUP_ROLES` | `group=ROLE,group=ROLE` | | how groups become roles (D12). An unmapped group grants nothing |
| `CANON_DATABASE_URL` | `scheme://host/database` | ● | the rebuildable index |
| `CANON_OBJECT_STORE_URL` | `scheme://host` | | the blob mirror |
| `CANON_LINK_EXPIRY_S` | a whole number of seconds | | how long a blob download link lasts |
| `CANON_WRITE_BACK_TIMEOUT_S` | a whole number of seconds | | how long one write-back may take before it abandons itself |
| `CANON_DRAIN_WINDOW_S` | a whole number of seconds | | how long a retiring instance may drain. **Must be longer than the one above** |

### `api` — optional

Absent means the feature is off — or, for the key cache, that its default
applies — not that the deployment is broken. The service starts, and everything
that needs a model reports itself **unavailable** on `/status`.

`CANON_AUTH_KEY_CACHE_TTL_S` is the one number D8 leaves to a deployment: the
identity provider's signing keys are cached for that long, so an outage of
CyberdyneAuth costs **new sign-ins and nothing else** — credentials already
issued keep verifying, readiness never consults it, and `/status` names it
unreachable. The cost is stated rather than hidden: a key rotated during an
outage is not honoured until the window ends.

| Variable | Shape | Secret | Default | What it is |
|---|---|:--:|---|---|
| `CANON_AUTH_KEY_CACHE_TTL_S` | a whole number of seconds | | 900 | how long cached signing keys keep verifying while CyberdyneAuth is unreachable (D8) |
| `CANON_LLM_ENABLED` | a switch | | off | the master switch (`project.md`) |
| `CANON_LLM_BASE_URL` | an OpenAI-compatible endpoint | | — | point it at the on-prem gateway from inside the deployment network |
| `CANON_LLM_API_KEY` | a bearer credential | ● | — | for that endpoint |
| `CANON_LLM_MODEL` | a model identifier | | — | passed through verbatim; no allow-list, no enum |
| `CANON_LLM_VISION_MODEL` | a model identifier | | — | the multimodal model for image description |
| `CANON_LLM_TIMEOUT_S` | a whole number of seconds | | 30 | half of the failure budget |
| `CANON_LLM_MAX_RETRIES` | a whole number of attempts | | 2 | the other half |

### `web` — required

| Variable | Shape | Secret | What it is |
|---|---|:--:|---|
| `PUBLIC_CANON_API_URL` | `scheme://host`, or empty for the same origin | | where the `api` application is served |
| `PUBLIC_CANON_AUTH_ISSUER` | `https://host/` | | CyberdyneAuth, the same issuer the `api` application verifies against |
| `PUBLIC_CANON_AUTH_CLIENT_ID` | the public client's identifier | | this application's registered browser client |
| `PUBLIC_CANON_AUTH_AUDIENCE` | the API's audience | | requested so the credential is accepted by `api`; omit where the issuer needs no audience |

`PUBLIC_` is the prefix the browser build carries, so none of these is a secret
and none may ever become one. **There is deliberately no client secret**: the
browser signs people in with an authorization code bound to a proof key it
generates (`auth-integration`), and a build that embedded a secret would be
publishing it.

Without the two required auth variables the application still serves every
screen and states that sign-in is unavailable — a misconfigured environment is
debuggable rather than blank. The redirect address is not configured: it is the
origin the person is on plus `/signed-in`, so a preview deployment cannot send
people back to production by inheriting a value.

The web application holds no credential of its own: a session's token is the
person's, obtained through CyberdyneAuth, and never an environment value.

### `postgres` and `minio`

Managed applications with their own credentials, which reach the `api`
application as `CANON_DATABASE_URL` and `CANON_OBJECT_STORE_URL`. Both are
**persistent volumes**, and both are **recoverable by rebuilding**: the index is
dropped, migrated and rebuilt from the working copies, and the blobs re-mirror
from them. There is no backup of either, deliberately — see
[`../docs/recovery.md`](../docs/recovery.md).

## Images: built once, promoted unchanged

Two images, one `Dockerfile` each, both in this directory:

| Image | File | What it runs |
|---|---|---|
| `api` | [`api.Dockerfile`](api.Dockerfile) | the FastAPI service, `python -m cybercanon.api` |
| `web` | [`web.Dockerfile`](web.Dockerfile) | the SvelteKit application on the node adapter (D10) |

**Nothing environment-specific is in either of them.** No endpoint, no
credential, no `.env`, no `ARG` carrying a setting — inspecting an image reveals
nothing about where it is running, which is the property that makes a digest
verified in pre-production mean something in production.
`tests/tooling/test_container_artifacts.py` asserts that by reading both files,
and `tests/tooling/test_secret_scan.py` searches the repository *and* the files
an image contains for credentials on every `just check`.

Nothing environment-specific reaches the **build context** either, which is the
half a `Dockerfile` cannot state on its own: the web image copies a whole
directory and SvelteKit reads a `.env` sitting in it at build time, so
[`../.dockerignore`](../.dockerignore) keeps environment files, machine state
and already-built output out of every build. The same suite asserts it, in both
directions — an environment file that would reach a build fails, and so does a
pattern broad enough to drop something the images copy.

An artifact is **built once per revision** and promoted between environments
without rebuilding. The build records its digest in
[`digests.json`](digests.json) against the revision it was built from, and the
promotion check compares what an environment is running against that record: a
rebuilt artifact fails it, naming both digests. Recording a *second, different*
digest for one revision is refused, which is the mechanism rather than the
warning — a promotion that rebuilt would have nowhere to write what it produced.

Three commands, each a `just` recipe over `tools/canon_release`, and each one's
exit code is the gate:

```
# the build pipeline's step, run immediately after an image is built
just release-record --image api --revision $GIT_SHA \
    --digest "$(docker image inspect --format '{{.Id}}' cybercanon-api:$GIT_SHA)"

# the promotion gate, before an environment is pointed at an artifact
just release-promotion --image api --revision $GIT_SHA \
    --running pre-production=sha256:... production=sha256:...
```

The digest is supplied rather than computed by the command, because the engine
that built the image is what knows it — and because every other question has to
stay answerable from a checkout, including on the day the platform is what is
broken.

**Rollback is a redeploy of a previously recorded digest**, never a rebuild:

```
just release-rollback --image api --revision $PREVIOUS_GIT_SHA
```

It prints the digest to deploy, and Coolify is pointed at that digest — deploy
revision N, then N-1, and what serves is the artifact that was already built and
already verified. A revision the ledger does not hold is reported instead of
quietly built, because an artifact nobody verified is not a rollback target. A
schema rollback is a different operation and is below: drop, migrate to the
previous version, rebuild.

## The release step, and the recovery when it fails

Migrations run **before any instance of the new version serves**, as Coolify's
pre-deploy command on the `api` application:

```
python -m cybercanon.api.migrate
```

It applies `db/migrations/NNNN_*.sql` in order, each file in its own
transaction, recording applied versions in `schema_migrations` (D4). It is
idempotent, so a retried deploy applies nothing. **Its exit code is the gate:** a
non-zero exit aborts the release, no instance of the new version starts, and the
previous version keeps serving. The failure message names the file that failed
and the version the schema is now at; `python -m cybercanon.api.migrate
--schema-version` asks the same question on its own.

**The image never migrates at start.** Its command serves and nothing else — an
entry point that migrated would migrate once per instance, and *"no instance
SHALL attempt a migration"* is the specified behaviour.

There is **no backup of the index**, deliberately (D5). The recovery for a
schema no migration can advance is `drop → migrate → rebuild`:

```
python -m cybercanon.api.recover /data/worktrees/<project>
```

which discards every table the migration set creates, applies the set to the
target version and rebuilds the index from the working copy, reporting progress
as it goes. A restore path would make the index authoritative in practice even
while `openspec/project.md` says it is not.

## Volumes

Three pieces of persistent state, and each one is recoverable by rebuilding it
from the remote repository rather than by restoring it.

| Volume | Mounted by | Path | Lost means | Recovered by |
|---|---|---|---|---|
| working copies | `api` | `/data/worktrees` | reads cannot be served for that project | a re-clone from the git host |
| index database | `postgres` | the managed application's data directory | lookups, listings and search are unavailable; specifications still answer | `drop → migrate → rebuild` from the working copy |
| blob mirror | `minio` | the managed application's data directory | previews and views are unavailable | a re-mirror from the working copy |

All three survive a restart, a redeploy and an artifact promotion: the state is
on the volume and the container is the thing being replaced. The procedures, the
expected durations and the drill that measures them are in
[`../docs/recovery.md`](../docs/recovery.md).

## Health, readiness and status

Three endpoints, and they answer three different questions (D2).

| Endpoint | Authenticated | What it means | Who reads it |
|---|:--:|---|---|
| `/healthz` | no | this process is running. It performs **no** input or output | the platform's liveness probe |
| `/readyz` | no | this process can serve its own requests | the platform's routing gate |
| `/status` | **yes** | per-project revisions, fetch times, index freshness, degraded dependencies | an operator |

**Readiness depends only on what this service owns.** A lost working copy
withholds traffic and names itself. A lost index, a lost blob mirror, an
unreachable model gateway, an unreachable identity provider and an unreachable
document platform **do not**: they are reported as degraded on `/status` and the
deploy completes. That is the whole point — another team's outage may not fail a
CyberCanon deploy, and git is the source of truth, so a lost index is a rebuild
rather than an incident.

Configure Coolify accordingly:

* **liveness probe → `/healthz`.** It is the only signal that may restart a
  container.
* **readiness gate → `/readyz`.** An instance reporting not-ready receives no
  traffic and **is not terminated for that reason alone**.
* **the web application's readiness is process-only.** It never calls the `api`
  application to decide whether it is ready, and a page whose data cannot be
  fetched renders an explicit unavailable state rather than an error (D10).

## Rollover: readiness gates it, and the drain window outlives a write-back

A deploy replaces instances without dropping a request, and it does that by
**overlapping** them (D7). Coolify starts the new instance, waits for `/readyz`,
routes to it, and only then signals the old one, which stops accepting new
requests and drains what it already accepted. A new version whose readiness
never reports ready is never routed to, so the deploy times out and the previous
version is still the one serving — nothing was replaced.

During the overlap **both instances mount the same working-copy volume on
purpose**, and it is the exclusive lock on that volume — not the number of
instances — that keeps a project single-writer (D6). A lock held in one
process's memory would be no lock at all for exactly the seconds that matter.

Two numbers make *"an interrupted write-back leaves a commit or leaves nothing"*
a property rather than a hope, and **their order is the whole mechanism**:

```
CANON_WRITE_BACK_TIMEOUT_S  <  CANON_DRAIN_WINDOW_S
```

A write-back accepted a moment before retirement begins either commits and
pushes inside the drain window and returns success, or hits its own timeout
first — and a timed-out write-back resets the working copy to the configured
branch — before anything terminates the process. Inverted, a container would be
killed holding a half-applied edit on the volume, which is the one state the
specification forbids. So the service **refuses to start** on an inverted pair,
naming both variables; it is not a paragraph anybody has to remember.

Configure Coolify to match:

* **readiness gate → `/readyz`**, with the new instance routed only once it
  answers ready;
* **stop grace period → `CANON_DRAIN_WINDOW_S`**, so the platform's window and
  the service's are the same number;
* **on startup the working copy is returned to the configured branch**,
  discarding any uncommitted change, which is what makes the abandoned case
  leave nothing behind rather than nothing *visible*.

Recovery when a volume is lost is a different operation and lives in
[`recovery.md`](recovery.md), with a measured duration per procedure.

## Logs

Structured JSON on stdout, one object per request, carrying a request id, the
acting actor when there is one and the project when there is one (D11). Coolify
collects stdout. Nothing ships logs anywhere else, and `X-Request-Id` is
honoured when a caller or a proxy sets one so that one request has one
identifier everywhere.

## Keeping this document honest

`tests/tooling/test_deploy_documents.py` asserts that the variables named here
and the settings the service actually declares are the same set, in both
directions. A variable added to the code and not to this table fails the build,
and so does one described here that nothing reads.
