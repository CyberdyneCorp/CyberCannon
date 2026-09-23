# Deploy brief — CyberCanon on Coolify

This file is the self-contained briefing for a session that arrives with **no
memory of this project** and has to deploy it. Read it, then read what it points
at, then deploy. It is the deployment counterpart of [`SPRINT.md`](SPRINT.md),
which does the same job for a sprint.

Everything below was checked against the repository on **2026-09-23**. Where a
claim could not be checked, it says so.

## Read first, in this order

1. [`deploy/go-live.md`](deploy/go-live.md) — **the worksheet.** What a human
   must obtain before anything is configured, a value per variable for
   pre-production, the exact identity requests, and the blockers found by
   probing the live services. This brief summarises it; that file is the detail.
2. [`deploy/README.md`](deploy/README.md) — **the reference.** What each
   variable *is*, how images are built once and promoted, what the release step
   is, what health/readiness/status mean, how rollover works.
3. [`deploy/coolify.yaml`](deploy/coolify.yaml) — the four applications as
   data: host, volumes, environment, health configuration, pre-deploy command,
   and the two surfaces that are never hosted with the reason each is absent.
4. [`deploy/recovery.md`](deploy/recovery.md) — the three recovery procedures,
   their expected durations, and the drill log.
5. `openspec/changes/add-coolify-deployment/specs/deployment-operations/spec.md`
   — the binding requirements. **Never edit it.** If it is wrong, report it.
6. `openspec/changes/add-coolify-deployment/design.md` — the numbered decisions
   (D1–D11) and, at the end, the **Migration Plan** reproduced in §6 below.
7. `openspec/changes/add-coolify-deployment/tasks.md` — 8.2 and 8.4 are the only
   unchecked boxes in the change.
8. `openspec/project.md` — architecture, and why PostgreSQL is a rebuildable
   index rather than a source of truth.

---

## 1. Scope — what deploys, and what deliberately does not

**Four applications, and exactly four** (D1), on the Cyberdyne Coolify instance
at `https://coolify.cyberdynecorp.ai` under the
`<service>.backend.coolify.cyberdynecorp.ai` convention:

| Application | What it is | Host | Volume |
|---|---|---|---|
| `api` | the FastAPI HTTP surface | `api.backend.coolify.cyberdynecorp.ai` | `/data/worktrees` |
| `web` | the SvelteKit application on the node adapter (D10) | `canon.backend.coolify.cyberdynecorp.ai` | none |
| `postgres` | the **rebuildable index** — never a source of truth | internal | `/var/lib/postgresql/data` |
| `minio` | the **blob mirror** — views, exports, preview GLBs | internal | `/data` |

**The `canon` command line and the FastMCP agent server are never hosted.** This
is a requirement with scenarios, not a preference. `deployment-operations` says
they *"SHALL NOT be deployed as network-reachable services, in any environment,
including behind authentication or on a private network"*, that the agent server
*"SHALL NOT listen on a network port"*, and that a request to expose it *"SHALL
be rejected as non-conforming"*. The reason is in the proposal: the agent server
is stdio and local-first by design, and hosting it would add an open port, a
CORS surface and a network threat model that local-first exists to avoid.

That exclusion is mechanical rather than remembered. `deploy/coolify.yaml`
names both under `never_hosted:` with the reason, and:

```
just deploy-check     # → "the declared deployment conforms: four components, and no fifth"
```

exits non-zero on a fifth application, on an application deploying the `canon`
binary or the agent server, on a host outside the convention, on a liveness
probe pointed at readiness, on a stateful component with no volume, on a stop
grace period that is not the drain window, and on a variable the manifest gives
that nothing reads. The same function runs inside `just check` through
`tests/tooling/test_deployment_inventory.py`.

---

## 2. Environment and tooling

**Docker lives at `$HOME/.docker/bin`, not on the default `PATH`.** Export it
first or the end-to-end and container suites **skip silently**, and a green run
then means only that nothing ran:

```bash
export PATH="$HOME/.docker/bin:$HOME/.local/bin:$PATH"
```

`uv` manages Python dependencies and `just` is the task runner (`just setup`).
Node is required for `just spec` and for the web build. The recipes that matter
here:

| Recipe | What it does |
|---|---|
| `just check` | lint, import contracts, complexity, features, adherence, web-check, tests, spec. CI runs this and nothing else |
| `just test-e2e` | Playwright over the web app plus `canon` subprocess runs; brings its own compose stack up. Outside `just check` on purpose |
| `just deploy-check` | `deploy/coolify.yaml` against the specification and against the settings the code declares |
| `just migrate` | the release step — `python -m cybercanon.api.migrate` |
| `just recover-index <working copy>` | `drop → migrate → rebuild` — `python -m cybercanon.api.recover` |
| `just drill …` | runs the three recovery drills and appends the measured durations to `deploy/recovery.md`. **It destroys the volumes it is pointed at** |
| `just drill-check` | the gate over that log: never drilled, older than 7 days, or slower than stated |
| `just release-record / release-promotion / release-rollback` | the digest ledger in `deploy/digests.json` |

---

## 3. Rules

1. **Never edit anything under `openspec/changes/*/specs/` or
   `openspec/specs/`.** The specs are frozen. Report a wrong one; never change
   one to make code or a deployment pass.
2. **Never weaken a test, skip a test, or relax a gate to get green.** If the
   honest fix is bigger than the scope, say so and leave it failing.
3. **Never write a credential into this repository** — not into a test, a
   fixture, a commit or a log. `just check` runs two secret scans, one over the
   git object database at every revision reachable from the default branch and
   one over the files the images contain
   (`tests/tooling/test_secret_scan.py`). A credential committed and then
   deleted is still found.
4. **Never mark a task done you did not verify.** An inflated count is worse
   than a low one.
5. **Configuration is the environment, and nothing else.** No file fallback, no
   `.env` beside a process, nothing environment-specific baked into an image. A
   value change is a restart, never a rebuild.
6. **`just drill` deletes a volume before it measures anything.** Never point it
   at production.

---

## 4. The gating item: identity

**Nothing is registered in CyberdyneAuth yet, and until it is, nobody can sign
in.** This is the one thing that blocks the deployment and it needs a human with
administrative access to the organisation's auth server.
[`deploy/go-live.md`](deploy/go-live.md) §1 has the full detail; this is the
shape and the requests.

### 4.1 What must exist

**One client, not two.** CyberCanon's browser application is a **public** client
using authorization code with PKCE, and `auth-integration` forbids it a secret:
*"no confidential client secret SHALL be required by or embedded in a
browser-delivered application"*. The API is **not a client at all** — it is a
resource server: it mints nothing, holds no credential of its own, and only
verifies. So what gets registered is the browser client plus the audience that
names the API.

| | Value to register |
|---|---|
| client id | `cybercanon-web` |
| client name | CyberCanon |
| client type | public (`token_endpoint_auth_method: none`) |
| grant types | `authorization_code` |
| response types | `code` |
| PKCE | required, `S256` — the only method the application offers |
| audience | `https://api.backend.coolify.cyberdynecorp.ai` |
| scopes | `openid profile email`, plus whatever scope carries groups and roles (§4.3) |

Redirect URIs are **derived** from the origin the person is on — always the
origin plus `/signed-in`, deliberately, so a preview deployment cannot send
people back to production by inheriting a value. Register one per environment:

```
https://canon.backend.coolify.cyberdynecorp.ai/signed-in          production
https://canon-pre.backend.coolify.cyberdynecorp.ai/signed-in      pre-production
http://localhost:5173/signed-in                                   a developer machine
```

There is no post-logout redirect: sign-out is local — it discards the credential
and the query cache — and never reaches `end_session_endpoint`.

### 4.2 The requests

Against the auth server's admin API, authenticated as an administrator. **Do not
paste a token into this repository.**

```bash
curl -sS -X POST https://auth.backend.coolify.cyberdynecorp.ai/api/v1/admin/oauth/clients \
  -H "Authorization: Bearer $CYBERDYNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "client_id": "cybercanon-web",
        "client_name": "CyberCanon",
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "require_pkce": true,
        "code_challenge_methods": ["S256"],
        "audience": ["https://api.backend.coolify.cyberdynecorp.ai"],
        "scope": "openid profile email",
        "redirect_uris": [
          "https://canon.backend.coolify.cyberdynecorp.ai/signed-in",
          "https://canon-pre.backend.coolify.cyberdynecorp.ai/signed-in",
          "http://localhost:5173/signed-in"
        ]
      }'

# read it back — this is where the audience string for three variables comes from
curl -sS https://auth.backend.coolify.cyberdynecorp.ai/api/v1/admin/oauth/clients \
  -H "Authorization: Bearer $CYBERDYNE_ADMIN_TOKEN"
```

Then **obtain one real token before deploying anything**, and decode it. The
authorization and token endpoints CyberdyneAuth publishes are:

```
https://auth.backend.coolify.cyberdynecorp.ai/api/v1/auth/oauth2/authorize
https://auth.backend.coolify.cyberdynecorp.ai/api/v1/auth/oauth2/token
```

That one payload settles `CANON_AUTH_AUDIENCE`, settles
`CANON_AUTH_GROUP_ROLES`, and answers B4 below.

### 4.3 The claims the token must carry

This is the half that decides whether anybody can read anything.

| Claim | Read by | What it decides | Absent means |
|---|---|---|---|
| `sub` | `actor_from` | the `ActorId` | the credential is **refused** (`NO_SUBJECT`) |
| `aud` | `Trust` | that the token was minted for *this* service | **refused** |
| `iss`, `exp` | `Trust` | issuer and validity | **refused** |
| `name` | `actor_from` | what the frame shows | the subject is shown instead |
| `groups` | `roles_from` | which `Role`s the actor holds | no roles: every mutating operation refuses, naming the role |
| `projects` | `Actor.may_see` | which projects the actor may read | **nothing is readable** |
| `tenant` | `tenants_agree` | the organisation | no tenancy question is asked |
| `git_emails` | `git_emails_from` | commit attribution | `.canon/actors.yaml` answers next |

Ask for `groups` and `projects` by those names. If CyberdyneAuth emits them
under other names, `ClaimNames` in
`libs/cybercanon/adapters/outbound/auth/claims.py` is the single place that
changes — seven fields (`subject`, `display_name`, `groups`, `projects`,
`tenant`, `git_emails`, `grant`), a value object rather than configuration.

`CANON_AUTH_GROUP_ROLES` maps the studio's group names onto the roles in
`cybercanon.domain.identity.Role`, which are **four**: `ART_DIRECTOR`,
`ARTIST`, `DESIGNER` and `ENGINEER`. Matching ignores surrounding space and
case. An unmapped group grants nothing and is **not an error** — a
configuration mistake may only ever grant less:

> `deploy/go-live.md` §1.5 says the roles are `ART_DIRECTOR` and `ARTIST`. That
> is drift: the enum has four members. Use the four.

```
CANON_AUTH_GROUP_ROLES=cybercanon-art-directors=ART_DIRECTOR,cybercanon-artists=ARTIST
```

---

## 5. Every environment variable an operator must supply

Thirty on `api`, four on `web`, none on `postgres` or `minio`. This set is
asserted in both directions against the settings the code declares and against
`deploy/coolify.yaml` by `tests/tooling/test_deploy_documents.py` and
`just deploy-check` — a variable missing here is a build failure, not a surprise
on the day. Shapes and full descriptions are in
[`deploy/README.md`](deploy/README.md); per-variable values for pre-production
are in [`deploy/go-live.md`](deploy/go-live.md) §2.

**⛔ = unknowable until the OAuth client of §4 exists. 🔒 = secret.**

### `api` — the fifteen it refuses to start without

| Variable | | What it is |
|---|:--:|---|
| `CANON_PROJECT` | | **the address.** Every resource is at `/v1/projects/<this>/…`; the entitlement decision, the index rows and the working-copy directory are keyed by it |
| `CANON_REPOSITORY_URL` | | the project's git remote |
| `CANON_REPOSITORY_BRANCH` | | the branch write-backs are committed to |
| `CANON_REPOSITORY_CREDENTIAL` | 🔒 | a deploy credential with **write** access — write-backs commit and push |
| `CANON_FETCH_INTERVAL_S` | | how often the scheduled fetch runs. The schedule is the guarantee; the webhook only shortens the wait |
| `CANON_WEBHOOK_SECRET` | 🔒 | what the git host signs its notifications with. The same string goes to the git host at step 7 |
| `CANON_AUTH_ISSUER` | | the CyberdyneAuth issuer, character for character as the discovery document gives it |
| `CANON_AUTH_AUDIENCE` | ⛔ | what this service is addressed as in a token. **Confirm against a real token** |
| `CANON_AUTH_KEY_SET_URL` | | where the signing keys are published |
| `CANON_AUTH_GROUP_ROLES` | ⛔ | `group=ROLE,group=ROLE` (§4.3) |
| `CANON_DATABASE_URL` | 🔒 | the rebuildable index, from the managed `postgres` application |
| `CANON_OBJECT_STORE_URL` | | the blob mirror, from the managed `minio` application |
| `CANON_LINK_EXPIRY_S` | | how long a blob download link lasts |
| `CANON_WRITE_BACK_TIMEOUT_S` | | how long one write-back may take before it abandons itself |
| `CANON_DRAIN_WINDOW_S` | | how long a retiring instance may drain. **Must be greater than the line above**, or the service refuses to start naming both |

The last pair is the whole interrupted-write-back mechanism, not a
recommendation: `CANON_WRITE_BACK_TIMEOUT_S < CANON_DRAIN_WINDOW_S` is what
makes a write-back either commit and push inside the drain window or time out
and reset the working copy — never leave a half-applied edit on the volume.
Coolify's **stop grace period must be `CANON_DRAIN_WINDOW_S`**, the same number.

### `api` — the fifteen whose absence is a feature being off

Absent means the feature is off, or that the default applies — not that the
deployment is broken. The service starts and reports the feature **unavailable**
on `/status`.

| Variable | | Default | Note |
|---|:--:|---|---|
| `CANON_AUTH_KEY_CACHE_TTL_S` | | 900 | how long cached signing keys keep verifying while CyberdyneAuth is unreachable (D8). An outage then costs new sign-ins and nothing else |
| `CANON_WORKING_COPIES` | | `/data/worktrees` | leave unset; the manifest mounts the volume there |
| `CANON_WEB_ORIGINS` | | — | **without it the web application shows an unavailable state against a perfectly healthy API.** The API and the application are on different hosts, so the application's origin has to be named. Never `*` — it is refused |
| `CANON_LLM_ENABLED` | | off | the master switch |
| `CANON_LLM_BASE_URL` | | — | the on-prem gateway, **from inside the deployment network**. `coolify.yaml` already declares `http://amini.backend.coolify.cyberdynecorp.ai/v1` |
| `CANON_LLM_API_KEY` | 🔒 | — | the gateway's bearer credential; a private gateway may need none |
| `CANON_LLM_MODEL` | | — | the text model, passed through verbatim — no allow-list, no enum |
| `CANON_LLM_VISION_MODEL` | | — | the multimodal model. **Task 8.2 is about this one** |
| `CANON_LLM_TIMEOUT_S` | | 30 | |
| `CANON_LLM_MAX_RETRIES` | | 2 | an authentication failure and an invalid request are never retried |
| `CANON_ARCHE_ENABLED` | | off | the document platform's master switch |
| `CANON_ARCHE_BASE_URL` | | — | reached with the **caller's own** credential, never a service one |
| `CANON_ARCHE_DEFAULT_WORKSPACE` | | — | where a document created from an asset page lands |
| `CANON_ARCHE_TIMEOUT_S` | | 5 | |
| `CANON_ARCHE_WEB_URL` | | the API root | where a person opens a document in a browser |

### `web` — four, all public, none a secret

| Variable | | What it is |
|---|:--:|---|
| `PUBLIC_CANON_API_URL` | | where the `api` application is served |
| `PUBLIC_CANON_AUTH_ISSUER` | | the same issuer `api` verifies against. **See B2** |
| `PUBLIC_CANON_AUTH_CLIENT_ID` | ⛔ | `cybercanon-web`, once registered |
| `PUBLIC_CANON_AUTH_AUDIENCE` | ⛔ | the same string as `CANON_AUTH_AUDIENCE`, or `api` refuses every credential this application obtains |

`PUBLIC_` is the prefix the browser build carries: none of these is a secret and
none may become one. **There is no client-secret variable and there could not
be.** The redirect address is not configured — it is the origin plus
`/signed-in`.

### `postgres` and `minio`

Managed applications. Their credentials reach `api` as `CANON_DATABASE_URL` and
`CANON_OBJECT_STORE_URL`. Both carry persistent volumes and **neither is backed
up, deliberately** — see §7.

---

## 6. The Migration Plan order (task 8.4)

This is the order in `openspec/changes/add-coolify-deployment/design.md`
(§ *Migration Plan*), with the confirmation each numbered step states. Greenfield: there is nothing to migrate from and no
cutover. Pre-production is stood up the same way, **from the same artifacts** —
`just release-promotion` is the gate that says an environment is running what
was recorded rather than a rebuild.

**1. Create the PostgreSQL and MinIO applications with their volumes.** Record
the connection settings as `CANON_DATABASE_URL` and `CANON_OBJECT_STORE_URL` on
the `api` application.
*Confirm:* both report healthy, and both volumes are mounted at the paths
`deploy/coolify.yaml` declares.

**2. Create the per-project working-copy volumes and the deploy credential; run
the initial clone.**
*Confirm:* `/status` reports a revision and a fetch time for the project. The
clone is done by the service itself on start and is re-entrant — a volume that
already holds a copy is adopted rather than re-obtained.

**3. Run the migration release command against the empty database.**
```
python -m cybercanon.api.migrate
python -m cybercanon.api.migrate --schema-version
```
*Confirm:* the second command reports the target version. A non-zero exit from
the first aborts the release: no instance of the new version starts and the
previous one keeps serving. The image **never** migrates at start.

**4. Deploy the API.**
*Confirm:* `/healthz` answers, `/readyz` answers ready, and `/status` refuses an
unauthenticated request. Then the sharper half — **deliberately misconfigure the
model gateway and the identity provider and confirm `/readyz` is still ready**,
with both named as degraded on `/status`. Readiness depends only on what this
service owns; another team's outage may not fail a CyberCanon deploy.

**5. Build the index for each project.**
```
python -m cybercanon.api.recover /data/worktrees/<project>
```
*Confirm:* `/status` reports the index in sync, naming the same revision as the
working copy. ⚠️ **B3 applies here** — also check that
`/v1/projects/<CANON_PROJECT>/assets` returns rows rather than `total: 0`.

**6. Deploy the web application.**
*Confirm:* it becomes ready **with the API stopped** — readiness is process-only
(D10) — and that a page then renders an explicit unavailable state rather than
an error.

**7. Register the git webhook.** Point it at `POST /hooks/repository` on the
`api` host, signing with `CANON_WEBHOOK_SECRET` in the `X-Canon-Signature`
header. A deployment with no webhook secret has no endpoint at all.
*Confirm:* a push advances the working-copy revision on `/status`, and both the
webhook and the schedule update `WorkingCopyStatus` identically.

**8. Sign in.** Not a numbered step — the plan predates the client existing. Do
it anyway before calling the environment stood up: open the application, sign
in, confirm the frame names the person and a project screen renders.
⚠️ **B2 applies here and this will fail until it is resolved.**

Afterwards the drills (`just drill`) run against this environment, and
`just drill-check` is the release pipeline's gate over their log.

### Health, readiness and status — configure Coolify accordingly

| Endpoint | Authenticated | What it means |
|---|:--:|---|
| `/healthz` | no | the process is running. It performs **no** input or output — point the liveness probe here, and only here |
| `/readyz` | no | this process can serve its own requests — the routing gate. An instance reporting not-ready receives no traffic and **is not terminated for that reason alone** |
| `/status` | **yes** | per-project revisions, fetch times, index freshness, degraded dependencies |

A lost working copy withholds traffic and names itself. A lost index, a lost
blob mirror, an unreachable model gateway, an unreachable identity provider and
an unreachable document platform **do not** — they are degraded on `/status` and
the deploy completes.

---

## 7. The three recovery drills

Three pieces of hosted state live on volumes and **every one of them is
derived**: git is the source of truth, PostgreSQL is a rebuildable index and
MinIO is a blob mirror. So losing a volume is a procedure to run, not an
incident to restore from. **There is no backup of the index and no backup of the
blob mirror, and there will not be one (D5)** — a restore path would make the
index authoritative in practice even while `openspec/project.md` says it is not.

| Procedure | Volume | Recovers from | Expected | Last measured |
|---|---|---|---|---|
| `working-copy-re-clone` | `/data/worktrees/<project>` | the git host | `10m` | **0.11s**, 2026-09-22, `developer` |
| `index-rebuild` | the `postgres` data directory | the working copy | `30m` | **0.04s**, 2026-09-22, `developer` |
| `blob-re-mirror` | the `minio` data directory | the working copy | `45m` | **0.18s**, 2026-09-22, `developer` |

**The order is not a preference.** The working copy is what the other two read,
so a lost working copy is re-cloned first; rebuilding an index from a copy that
is not there yet measures an error path rather than a recovery. The two derived
procedures are independent of each other and are per project.

* **`working-copy-re-clone`** — restarting the `api` application is the whole
  procedure: the boot step returns every project's working copy to its
  configured branch, reporting every local commit it discards. That is also what
  makes an instance killed mid-write-back leave nothing half-applied behind.
* **`index-rebuild`** — `drop → migrate → rebuild`, one command:
  `python -m cybercanon.api.recover /data/worktrees/<project>`. It runs through
  the same `rebuild_index` use case the command line and the service call, so
  there is no second implementation that would recover a different index.
* **`blob-re-mirror`** — a blob's key is the digest of its content, so every
  object lands under the key it had before and every predating reference keeps
  resolving.

**The measured durations above are a floor, not an estimate for a studio
repository.** They come from the suite that runs all three against real git, a
real PostgreSQL and a real S3 API on **one fixture project** on a developer
machine, and they exist so a regression in the *procedure* is visible. The
number an on-call engineer plans around is the pre-production one, and **no
pre-production drill has ever been recorded** — the drill log holds three
`developer` rows and nothing else. Producing those rows is part of standing
pre-production up.

A scheduled job runs all three against pre-production every **7 days**,
destroying the volume first so the procedure meets a real loss:

```
just drill --project <project> --working-copy /data/worktrees/<project> --blobs /data/blobs
just drill-check
```

`just drill-check` fails when a procedure has never been drilled, when its most
recent drill is older than 7 days, or when it took longer than the expected
duration. **A drill that overran is the signal to change the architecture, not
the signal to add backups.** It is deliberately not in `just check`: staleness is
a function of today's date rather than of the change under review.

---

## 8. What is known-broken or unverified

Four blockers were established against the live services on 2026-09-23. **None
is a guess and none can be worked around by configuration alone.** Read this
before writing any environment variable. Full detail is in
[`deploy/go-live.md`](deploy/go-live.md) §0.

### B1 — CyberCanon has no OAuth client, so no correctly-audienced token exists

`Trust` requires both an issuer and an audience: *"a token minted elsewhere is
not a session"*. A CyberArche-issued token was presented and correctly refused —
it carries no `aud` claim. Until the client of §4 exists, nothing can sign in
and `CANON_AUTH_AUDIENCE`, `PUBLIC_CANON_AUTH_CLIENT_ID` and
`PUBLIC_CANON_AUTH_AUDIENCE` are unknowable. **This is the gating item.**

### B2 — the web application asks CyberdyneAuth at paths it does not serve

`apps/cybercanon/web/src/lib/config.ts` builds both endpoints from the issuer
with **fixed paths**:

```ts
export const AUTHORIZE_PATH = '/authorize';
export const TOKEN_PATH = '/oauth/token';
```

Those are `tools/canon_issuer`'s paths. CyberdyneAuth publishes
`/api/v1/auth/oauth2/authorize` and `/api/v1/auth/oauth2/token`; both fixed
paths were observed to 404. **There is no value of `PUBLIC_CANON_AUTH_ISSUER`
that fixes this** — any prefix that makes `/authorize` resolve leaves the token
address wrong, because the two published paths do not share a suffix shape.

The honest fix is that the application reads `/.well-known/openid-configuration`
and takes `authorization_endpoint` and `token_endpoint` from it. That is a
frontend change with its own tests and it was reported rather than attempted.
**Sign-in through the browser cannot work in production until it is made.**

### B3 — the documented index rebuild keys rows by the wrong project

`deploy/README.md` and `docs/recovery.md` both give the recovery as
`python -m cybercanon.api.recover /data/worktrees/<project>`.
`services/cybercanon/api/recover.py` calls `rebuild_index("")` and passes **no**
`project=`, so rows are keyed by the `name:` declared in the working copy's
`.canon/project.yaml` — while the hosted surface reads rows keyed by
`CANON_PROJECT`.

Observed end to end in the e2e stack with `CANON_PROJECT=ronin` and
`name: Ronin`: the recovery reported *"rebuilt 1 project(s), 1 asset(s)"*, the
row landed under `Ronin`, and `/v1/projects/ronin/assets` answered `total: 0`
for ever after. `rebuild_index` **already takes** `project=` and documents it as
existing for exactly this reason, so the gap is in the entry point, not the use
case. Which name wins is a decision for the specification's owner, which is why
it is reported rather than changed.

**This blocks Migration Plan step 5** whenever `CANON_PROJECT` and the declared
name differ — including by case alone, which is the case in `examples/ronin`.

### B4 — the group and project claims are not in `claims_supported`

CyberdyneAuth's discovery document lists `sub iss aud exp iat auth_time nonce
email email_verified name picture`. The adapter reads `groups`, `projects`,
`tenant` and `git_emails`. A credential carrying none of them resolves to an
actor with **no roles and no projects** — not a refusal, by design, but a person
who can read nothing. `claims_supported` is advisory rather than exhaustive in
OIDC, so this is an **open question for registration**, settled by the first
correctly-audienced token.

### Also unverified

* **The digest ledger is empty.** `deploy/digests.json` is `[]`, so no artifact
  has been built and recorded. `just release-promotion` has nothing to compare
  against, and `just release-rollback` on any revision reports *"has no recorded
  digest, so rolling back to it would mean building an artifact nobody
  verified"* — correct behaviour, but it means **the first build of the first
  revision must run `just release-record`** or the promotion story starts empty.
* **No deployment exists.** Every claim in §6 and §7 has been verified against
  code, tests and a local compose stack, and **none of it against Coolify**.
* **No signed-in screen had ever been asserted by an end-to-end test until this
  run.** `deploy/e2e/compose.yaml` pointed `CANON_AUTH_KEY_SET_URL` at an
  address on the `api` that nothing served — the catch-all refuses any path
  carrying no surface version, the key set retrieval answered 400, and no
  credential could ever verify. **Every browser assertion this project had ever
  made was therefore made about a signed-out page.** The stack now runs
  `tools/canon_issuer` as a service of its own (`deploy/e2e/issuer.Dockerfile`)
  and `tests/e2e/test_web_signed_in.py` drives the real flow — button, redirect
  out, code exchange, credential, screen. The signed-in images in
  `docs/screenshots/` that predate this run needed an issuer bolted on from the
  host; 01 through 14 have been re-captured from the stack as it now ships.
* **`tests/e2e/test_web_signed_in.py` does not prove B2, and cannot.** The
  stack's issuer serves `tools/canon_issuer`'s paths, which are the paths the
  application has hard-coded. A stack whose issuer published CyberdyneAuth's
  paths would fail the sign-in — and that is the test worth having once B2 is
  fixed.
* **The index rebuild after bringing the e2e stack up is manual**, because of
  B3. It is not a `just` recipe, deliberately: a recipe that silently depended
  on somebody having run a command by hand would be a recipe that misleads.
* **Two documentation drifts were found and one was fixed this run.**
  `deploy/README.md` pointed at `docs/recovery.md` for *"the procedures, the
  expected durations and the drill that measures them"* — those live in
  `deploy/recovery.md`; `docs/recovery.md` answers a different question and has
  no drill log. That link now points at both with the distinction stated. The
  one left alone: `deploy/go-live.md` §1.5 says the role set is `ART_DIRECTOR`
  and `ARTIST`, and `cybercanon.domain.identity.Role` has four members (§4.3).

---

## 9. The two open tasks

These are the only unchecked boxes in
`openspec/changes/add-coolify-deployment/tasks.md`. **Both need the real
environment**, which is why they are still open.

### 8.2 — point the model endpoint at the on-prem gateway

> *Point the model endpoint at the on-prem gateway from inside the deployment
> network and verify a test that concept images are described without egress to
> a third-party endpoint.*

**Needs:** `CANON_LLM_ENABLED`, `CANON_LLM_BASE_URL`, `CANON_LLM_API_KEY`,
`CANON_LLM_MODEL` and `CANON_LLM_VISION_MODEL` set per §5 and a redeploy — a
value change is a restart, never a rebuild.

**Confirm:**
1. `/status` reports the `language_model` component as `available` rather than
   `unavailable`;
2. ingest a concept image and a description comes back;
3. **the half the task is actually about** — no egress to a third-party
   endpoint. `CANON_LLM_BASE_URL` is an internal Coolify address, so the check is
   that the `api` application's egress shows traffic to `amini.backend…` and to
   nothing outside the estate for the duration of the description.

`tests/integration/test_model_endpoint.py` exercises the gateway from a machine
that can reach it. It skips with `CANON_LLM_ENABLED` unset — the default
everywhere — and says so per test rather than reporting green over nothing.

### 8.4 — stand up pre-production from the same artifacts

> *Stand up pre-production from the same artifacts following the Migration Plan
> order, and verify each numbered step's stated confirmation.*

**Needs:** the OAuth client of §4 (B1), a resolution for B2 before step 8 can
pass, a resolution for B3 before step 5 can pass on a project whose declared
name differs from its address, a git deploy credential with write access, a
webhook secret, and the managed `postgres` and `minio` applications.

**Done is:** every numbered step in §6 confirmed as written — including the
deliberate misconfiguration at step 4 and the API-stopped readiness at step 6 —
and the three drills of §7 run **against pre-production** so the log carries a
row per procedure for that environment rather than three `developer` rows.

---

## 10. What "done" looks like

1. `just check` green. Report its runtime and test count.
2. `just deploy-check` and `just drill-check` green.
3. `just test-e2e` green **with Docker on the `PATH`** — a run that skipped is
   not a run.
4. Every numbered Migration Plan step confirmed, or named as blocked with which
   blocker of §8 blocks it.
5. `tasks.md` updated only for what was verified. 8.2 and 8.4 stay unchecked
   until their confirmations actually happened.
6. Any spec problem found reported, never edited.
