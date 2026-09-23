# Going live on the Cyberdyne Coolify instance

Everything a session arriving with **no context** needs in order to deploy
CyberCanon, in the order it is needed. [`README.md`](README.md) is the reference
— what each variable *is*, how images are promoted, what recovery means. This is
the **worksheet**: what a human must obtain, what to put in each box, what to
confirm at each step, and — stated first, because it is what actually blocks —
what does not work yet.

Two tasks in `openspec/changes/add-coolify-deployment/tasks.md` are open and both
need the real environment:

* **8.2** — point the model endpoint at the on-prem gateway from inside the
  deployment network and verify concept images are described with no egress to a
  third-party endpoint;
* **8.4** — stand up pre-production from the same artifacts, in the Migration
  Plan's order, confirming each numbered step.

Everything else is implemented and checked. `just check` and `just test-e2e` are
green.

---

## 0. Blockers found by probing the real services

These were established against the live CyberdyneAuth on 2026-09-23. None of
them is a guess, and none of them can be worked around by configuration alone.
**Read this section before writing any environment variable.**

### B1 — resolved: CyberCanon had no OAuth client, so no correctly-audienced token existed

**Resolved.** The public PKCE client `cyb_5UIdba7PWtBo1MmH` is registered, and a
real sign-in obtains an access token with `aud=cybercanon`. §1 records the
registration as it actually is.

`Trust` requires both an issuer and an audience, and says why:

> an audience is required: a token minted elsewhere is not a session

A CyberArche-issued token was presented and **correctly refused**: it carries no
`aud` claim. That refusal is the design working. Until a client exists for
CyberCanon (§1), nothing can sign in, and the values of
`CANON_AUTH_AUDIENCE`, `PUBLIC_CANON_AUTH_CLIENT_ID` and
`PUBLIC_CANON_AUTH_AUDIENCE` are unknowable.

### B2 — resolved: the web application asked CyberdyneAuth at paths it does not serve

Before the fix, `apps/cybercanon/web/src/lib/config.ts` built both endpoints
from the issuer with **fixed paths** (since removed):

```ts
// before the fix
export const AUTHORIZE_PATH = '/authorize';
export const TOKEN_PATH = '/oauth/token';
```

Those were `tools/canon_issuer`'s paths. CyberdyneAuth publishes:

| | Published | What the application asked for |
|---|---|---|
| authorization | `/api/v1/auth/oauth2/authorize` | `/authorize` → **404** |
| token | `/api/v1/auth/oauth2/token` | `/oauth/token` → **404** |

Both 404s were observed directly. **There was no value of
`PUBLIC_CANON_AUTH_ISSUER` that fixed this**: any prefix that made `/authorize`
resolve left the token address wrong, because the two paths do not share a
suffix shape.

**Resolved** (`openspec/changes/fix-web-oidc-discovery`). Fixing the paths
alone would not have been enough: CyberdyneAuth sends no
`Access-Control-Allow-Origin` for the application's origin, so a browser can
read neither the discovery document nor a token response. The in-browser token
exchange failed with *"Failed to fetch"* even against the right path. So the
application's **server** now does both:

* `GET /auth/authorize` reads `<issuer>/.well-known/openid-configuration`, checks
  that its `issuer` is the configured one, and redirects the browser to the
  `authorization_endpoint` it names with the browser's query unchanged;
* `POST /auth/token` relays the code exchange and the refresh grant to the
  `token_endpoint` it names. It remains a public client: the proof key stays in
  the browser, no secret is added, and nothing is kept;
* `GET /auth/end-session` redirects to the `end_session_endpoint` it names.

The fixed paths are gone. The issuer is the only address configured. Checked
against the live CyberdyneAuth on 2026-09-23: sign-in, the refresh grant and
sign-out all worked end to end from `http://localhost:5173`.

### B3 — the documented index rebuild keys rows by the wrong project — **resolved**

`deploy/README.md` and `docs/recovery.md` both gave the recovery as:

```
python -m cybercanon.api.recover /data/worktrees/<project>
```

`services/cybercanon/api/recover.py` called `rebuild_index("")` and passed **no**
`project=`, so rows were keyed by the `name:` declared in the working copy's
`.canon/project.yaml`. The hosted surface reads rows keyed by `CANON_PROJECT`,
which `deploy/e2e/compose.yaml` is explicit is *"deliberately not derived from
the repository URL or from `.canon/project.yaml`, which disagree"*.

Observed end to end in the e2e stack: with `CANON_PROJECT=ronin` and
`name: Ronin`, the recovery reported *"rebuilt 1 project(s), 1 asset(s)"*, the
row landed under `Ronin`, and `/v1/projects/ronin/assets` answered `total: 0`
for ever after.

**Resolved in the entry point, where the gap was.** The rebuild now keys rows by
the working copy's **directory name**, which is the identifier the deployment
serves the project at: `GitRepositoryHost.path(project)` is `<volume>/<project>`,
so the path in the documented command already carries the answer and the command
itself does not change. `rebuild_index` always took `project=`; nothing about the
use case moved, and `canon index` on a laptop still keys by the declared name
because it has no address.

The regression test is
`tests/integration/test_recovery_drills.py::test_the_index_recovery_keys_rows_by_the_name_the_deployment_serves`,
and it stages a working copy that **declares a different name from the one it is
served at** — which is the whole reason this suite passed for as long as it did.
Every other fixture in it declares `name: ronin` in a directory called `ronin`,
so the rebuild keyed rows correctly by accident and no assertion could tell.

### B4 — the group and project claims are not in `claims_supported` — **resolved**

CyberdyneAuth's discovery document lists:

```
"claims_supported": ["sub","iss","aud","exp","iat","auth_time","nonce",
                     "email","email_verified","name","picture"]
```

`cybercanon.adapters.outbound.auth.claims` reads `groups` for roles, `projects`
for entitlement, `tenant` and `git_emails`. A credential carrying none of them
resolves to an actor with **no roles and no projects** — which is not a refusal,
by design, but is a person who can read nothing. `roles` and `roles:read` are in
`scopes_supported`, so the facts exist under some name.

*Observed since, with the registered client:* the access token carries `roles`
prefixed with the client id, and carries no `groups` and no `projects`.

**The API now reads the token the issuer really emits**, and the three things
that changed are configuration rather than code:

* roles come from `roles`, keeping only the entries prefixed with
  `CANON_AUTH_CLIENT_ID` and stripping the prefix before
  `CANON_AUTH_GROUP_ROLES` maps them. `roles` covers **every** client the person
  holds a role on, so an unfiltered reader would hand somebody this project's
  art director because they are an art director in another application;
* entitlement is `orgs` **and** roles: a person reads `CANON_PROJECT` only when
  their `orgs` claim carries `CANON_AUTH_ORG_ID` *and* they hold at least one
  role on this client. Not `org` (that is their *primary* organisation, so
  keying on it would lock out a member whose primary is elsewhere), not
  `entitlements` (billing products), not `github_login` (nullable, and null for
  the only organisation today), and `is_admin` does not bypass it;
* automation is `type: "service"` with a `sub` of `client:<id>`. The `gty` claim
  the adapter used to read was a guess and is gone.

A credential carrying no `roles` claim at all is **refused** rather than read as
"holds nothing": an absent claim means the identity service did not answer, and
this is the one place where the sign-in's scope matters — the scope must include
`roles`, which is why `openid profile email offline_access roles` is the default
in both the web application and `canon`.

Two new required settings come with it, `CANON_AUTH_CLIENT_ID` and
`CANON_AUTH_ORG_ID`; both are in §2's worksheet. A deployment missing either
starts, signs people in and shows them nothing, which is why they are required
rather than optional.

---

## 1. The identity story

**The client is registered** (B1). The tables below record what exists. The
requests in §1.4 are kept as the template for another environment. Registering a
client on the organisation's auth server is the human's call.

### 1.1 What must exist

One client, not two. CyberCanon's browser application is a **public** client
using authorization code with PKCE, and `auth-integration` forbids it a secret:

> no confidential client secret SHALL be required by or embedded in a
> browser-delivered application

The API is not a client at all: it is a **resource server**. It mints nothing,
holds no credential of its own, and only verifies. So what is registered is the
browser client plus the audience that names the API.

| | Value to register |
|---|---|
| client id | `cyb_5UIdba7PWtBo1MmH` (registered) |
| client name | CyberCanon |
| client type | public (`token_endpoint_auth_method: none`) |
| grant types | `authorization_code`, `refresh_token` |
| response types | `code` |
| PKCE | required, `S256` (the only method the application offers, and the only one CyberdyneAuth accepts) |
| audience | `cybercanon`, which is bound to the client registration. CyberdyneAuth ignores the `audience` request parameter |
| scopes | `openid profile email offline_access roles` (what `DEFAULT_SCOPE` requests). `offline_access` is what returns a refresh token, and without it every session lapses with its 15-minute access token |
| CORS | none needed. The browser never calls CyberdyneAuth cross-origin, because the application's server relays discovery and the token exchange (B2) |

### 1.2 Redirect URIs

The application **derives** the redirect address from the origin the person is
on, deliberately, so that *"a preview deployment cannot send people back to
production by inheriting a value"*. It is always the origin plus `/signed-in`.
Register one per environment that exists:

```
https://canon.backend.coolify.cyberdynecorp.ai/signed-in          production
https://canon-pre.backend.coolify.cyberdynecorp.ai/signed-in      pre-production
http://localhost:5173/signed-in                                   a developer machine
```

Sign-out ends the CyberdyneAuth session too: after discarding the credential
and the query cache, the browser posts the identity token to the application's
`/auth/end-session`, which sends it on to `end_session_endpoint` with `client_id`
and `id_token_hint` (posted, so the token stays out of access logs and history). Without that, the next person on a shared machine was signed
straight back in as the previous one. **Still to register (human step):** the
post-logout redirect URIs, one per origin plus `/`:

```
https://canon.backend.coolify.cyberdynecorp.ai/
https://canon-pre.backend.coolify.cyberdynecorp.ai/
http://localhost:5173/
```

CyberdyneAuth refuses an unregistered `post_logout_redirect_uri` outright
(*"post_logout_redirect_uri is not registered for this client"*), so the
application sends none until `CANON_AUTH_POST_LOGOUT_REDIRECT=true` is set on
`web`. Until then, sign-out ends on CyberdyneAuth's own "You have been signed
out" page.

### 1.3 The claims the token carries

This is the half that decides whether anybody can read anything, and these are
the claims **CyberdyneAuth actually emits**, verified against production. The
version of this table that listed `groups`, `projects`, `tenant` and
`git_emails` described a token the issuer has never sent — and the suites agreed
with it because the fixtures minted that shape too.

| Claim | Read by | What it decides | Absent means |
|---|---|---|---|
| `sub` | `actor_from` | the `ActorId`; `client:<id>` on a service token | the credential is **refused** (`NO_SUBJECT`) |
| `aud` | `Trust` | that this token was minted for *this* service | **refused** |
| `iss`, `exp` | `Trust` | issuer and validity | **refused** |
| `type` | `actor_from` | `access` is a person, `service` is automation | **refused** — a shape this cannot read is not a session |
| `roles` | `roles_from` | which `Role`s the actor holds, from the entries prefixed `<CANON_AUTH_CLIENT_ID>:` | **refused**: an absent claim means the identity service did not answer, which is not the same as holding nothing |
| `orgs` | entitlement | whether the person belongs to `CANON_AUTH_ORG_ID`, matched on `id` | **nothing is readable** — and `orgs: []` is the same answer |
| `org` | — | **deliberately not read**: the person's *primary* organisation only, so keying on it would lock out a member whose primary is elsewhere | — |
| `entitlements` | — | **deliberately not read**: billing products (`pro:monthly`), never access | — |
| `is_admin` | — | **deliberately not read**: an admin flag does not widen access | — |

There is **no `name`, no `email` and no `git_emails`** on an access token: a
surface shows the subject, and commit attribution comes from `.canon/actors.yaml`
(D13). The web frame reads `name` and `email` from the **id token**, which is
where CyberdyneAuth puts them.

A person reads `CANON_PROJECT` if and only if their `orgs` claim carries
`CANON_AUTH_ORG_ID` **and** their `roles` claim holds at least one entry
prefixed with `CANON_AUTH_CLIENT_ID`. Membership alone is not access, and a role
alone is not membership.

The sign-in must request the `roles` scope —
`openid profile email offline_access roles`, the default in both the web
application and `canon` — because a token without the claim is refused rather
than read as a person who holds nothing.

If CyberdyneAuth ever emits these under other names, `ClaimNames` in
`libs/cybercanon/adapters/outbound/auth/claims.py` is the single place that
changes: six fields, a value object rather than configuration. What a deployment
sets is `CANON_AUTH_CLIENT_ID`, `CANON_AUTH_ORG_ID` and the role mapping.

### 1.4 The requests

Admin API, authenticated as an administrator of the auth server. **Do not paste
a token into this repository** — `just check` runs two secret scans over the
object database and over what the images contain.

Register the client:

```bash
curl -sS -X POST https://auth.backend.coolify.cyberdynecorp.ai/api/v1/admin/oauth/clients \
  -H "Authorization: Bearer $CYBERDYNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "client_name": "CyberCanon",
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "require_pkce": true,
        "code_challenge_methods": ["S256"],
        "audience": ["cybercanon"],
        "scope": "openid profile email offline_access roles",
        "redirect_uris": [
          "https://canon.backend.coolify.cyberdynecorp.ai/signed-in",
          "https://canon-pre.backend.coolify.cyberdynecorp.ai/signed-in",
          "http://localhost:5173/signed-in"
        ],
        "post_logout_redirect_uris": [
          "https://canon.backend.coolify.cyberdynecorp.ai/",
          "https://canon-pre.backend.coolify.cyberdynecorp.ai/",
          "http://localhost:5173/"
        ]
      }'
```

Read it back, and keep the answer — it is where the audience string that goes
into three environment variables actually comes from:

```bash
curl -sS https://auth.backend.coolify.cyberdynecorp.ai/api/v1/admin/oauth/clients \
  -H "Authorization: Bearer $CYBERDYNE_ADMIN_TOKEN"
```

Then prove a credential is obtainable and carries what §1.3 needs, before
deploying anything. The token endpoint accepts an `audience` parameter:

```bash
# in a browser, or by hand with a verifier you generated:
open "https://auth.backend.coolify.cyberdynecorp.ai/api/v1/auth/oauth2/authorize?\
response_type=code&client_id=$CLIENT_ID&\
redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Fsigned-in&\
scope=openid%20profile%20email%20offline_access%20roles&state=$STATE&\
code_challenge=$CHALLENGE&code_challenge_method=S256"

curl -sS -X POST https://auth.backend.coolify.cyberdynecorp.ai/api/v1/auth/oauth2/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "grant_type=authorization_code&code=$CODE&client_id=$CLIENT_ID" \
  -d "redirect_uri=http://localhost:5173/signed-in&code_verifier=$VERIFIER"
```

**Decode the `access_token` and read its claims.** That one payload answers B4,
fixes `CANON_AUTH_AUDIENCE`, and tells you what to write in
`CANON_AUTH_GROUP_ROLES`.

### 1.5 `CANON_AUTH_GROUP_ROLES`, `CANON_AUTH_CLIENT_ID` and `CANON_AUTH_ORG_ID`

The mapping is configuration and names no role key in code, so *"adding a
mapping is a configuration change rather than a deploy"*. The right-hand side
must be a `Role`; a value that is not one contributes nothing, because a
configuration mistake may only ever grant **less**.

The roles are `ART_DIRECTOR`, `ARTIST`, `DESIGNER` and `ENGINEER`
(`cybercanon.domain.identity.Role` — four members, not two; earlier revisions of
this page said two and that was drift). Write the studio's role keys **without
the client-id prefix** on the left — the token says `<client id>:art_director`,
and the API strips the prefix before it looks anything up:

```
CANON_AUTH_GROUP_ROLES=art_director=ART_DIRECTOR,artist=ARTIST
```

An unmapped key grants nothing and is **not** an error — which is what makes a
mapping mistake look like what it is rather than like an outage.

`CANON_AUTH_CLIENT_ID` is the same client id the browser application is given as
`PUBLIC_CANON_AUTH_CLIENT_ID` (§1.1). It is what tells the API which entries of
the one `roles` claim are its own.

`CANON_AUTH_ORG_ID` is the **`id`** of the organisation this deployment serves,
read from the `orgs` claim of the token decoded above — the opaque identifier,
not `short_name` and not `github_login`, which is null for the organisation that
exists today. It is not written down in this repository, and nothing in the
product knows it: a person reads the project only when their `orgs` claim
carries this id and they hold a role on the client above.

---

## 2. The worksheet

Thirty-four settings on `api`, four on `web`. This table is the same set as
[`README.md`](README.md)'s and as [`coolify.yaml`](coolify.yaml)'s — that is
asserted in both directions by `tests/tooling/test_deploy_documents.py` and
`just deploy-check`, so a variable missing here is a build failure and not a
surprise on the day.

**⛔ = cannot be known until the OAuth client of §1 exists.**

### `api` — the seventeen it refuses to start without

| Variable | | Value for pre-production |
|---|:--:|---|
| `CANON_PROJECT` | | `ronin` — the address the project is served at, and the directory its working copy is kept in. It no longer has to equal the `name:` in `.canon/project.yaml` (B3) |
| `CANON_REPOSITORY_URL` | | the project's git remote, e.g. `https://git.cyberdynecorp.ai/cyberdyne/ronin.git` |
| `CANON_REPOSITORY_BRANCH` | | `main` |
| `CANON_REPOSITORY_CREDENTIAL` | 🔒 | a deploy credential with **write** access — write-backs commit and push |
| `CANON_FETCH_INTERVAL_S` | | `300`. The schedule is the guarantee; the webhook only shortens the wait |
| `CANON_WEBHOOK_SECRET` | 🔒 | generate one, and give the same string to the git host in step 7 |
| `CANON_AUTH_ISSUER` | | `https://auth.backend.coolify.cyberdynecorp.ai` — the `issuer` in the discovery document, character for character |
| `CANON_AUTH_AUDIENCE` | | `cybercanon` — the audience bound to the client registration (§1.1), read off a real token's `aud`. It is **not** the API's URL: an earlier revision of this line expected one, and the token settled it |
| `CANON_AUTH_CLIENT_ID` | | the client registered in §1.1 — the same string as `PUBLIC_CANON_AUTH_CLIENT_ID`. The API keeps only the `roles` entries carrying this prefix |
| `CANON_AUTH_ORG_ID` | ⛔ | §1.5 — the `id` of the organisation in the token's `orgs` claim. Get it from the decoded token of §1.4; it is nowhere in this repository |
| `CANON_AUTH_KEY_SET_URL` | | `https://auth.backend.coolify.cyberdynecorp.ai/.well-known/jwks.json` |
| `CANON_AUTH_GROUP_ROLES` | ⛔ | §1.5 — needs the role keys a real token carries, written without the client-id prefix |
| `CANON_DATABASE_URL` | 🔒 | from the managed PostgreSQL application, created in step 1 |
| `CANON_OBJECT_STORE_URL` | | from the managed MinIO application, created in step 1 |
| `CANON_LINK_EXPIRY_S` | | `900` |
| `CANON_WRITE_BACK_TIMEOUT_S` | | `30` |
| `CANON_DRAIN_WINDOW_S` | | `60` — **must be greater than the line above**, or the service refuses to start naming both |

### `api` — the seventeen whose absence is a feature being off

| Variable | | Default | Value for pre-production |
|---|:--:|---|---|
| `CANON_AUTH_KEY_CACHE_TTL_S` | | 900 | leave unset. An identity-service outage then costs new sign-ins and nothing else |
| `CANON_WORKER_CLIENT_ID` | | — | leave unset unless a client-credentials client exists for background work. With it, the scheduled validation pass obtains a service credential of its own and is recorded as the subject it resolves to; without it the pass runs and is recorded as `automation`, exactly as it does today |
| `CANON_WORKER_CLIENT_SECRET` | 🔒 | — | that client's secret. Set it **with** the id or not at all: half the pair behaves like the absence |
| `CANON_WORKING_COPIES` | | `/data/worktrees` | leave unset; the manifest mounts the volume there |
| `CANON_WEB_ORIGINS` | | none | `https://canon-pre.backend.coolify.cyberdynecorp.ai`. **Without it the application shows an unavailable state against a perfectly healthy API.** Never `*` — it is refused |
| `CANON_LLM_ENABLED` | | off | `true` — this is task 8.2 |
| `CANON_LLM_BASE_URL` | | — | `http://amini.backend.coolify.cyberdynecorp.ai/v1`, already the value in [`coolify.yaml`](coolify.yaml). It is an **internal** address on purpose: that is what keeps unreleased concept art on the premises |
| `CANON_LLM_API_KEY` | 🔒 | — | the gateway's bearer credential |
| `CANON_LLM_MODEL` | | — | the text model the gateway serves, passed through verbatim |
| `CANON_LLM_VISION_MODEL` | | — | the multimodal model. **8.2 is about this one**: it is what describes a concept image |
| `CANON_LLM_TIMEOUT_S` | | 30 | leave unset |
| `CANON_LLM_MAX_RETRIES` | | 2 | leave unset |
| `CANON_ARCHE_ENABLED` | | off | `true` if linked documents are wanted in pre-production |
| `CANON_ARCHE_BASE_URL` | | — | CyberArche's API root. Reached with the **caller's own** credential, never a service one |
| `CANON_ARCHE_DEFAULT_WORKSPACE` | | — | the workspace a document created from an asset page lands in |
| `CANON_ARCHE_TIMEOUT_S` | | 5 | leave unset |
| `CANON_ARCHE_WEB_URL` | | the API root | where a person opens a document in a browser |

Credentials and endpoints for a live CyberArche exist **outside this repository**
and are deliberately not written down here.

### `web` — four, all public, none a secret, and two optional server-only settings

| Variable | | Value for pre-production |
|---|:--:|---|
| `PUBLIC_CANON_API_URL` | | `https://api.backend.coolify.cyberdynecorp.ai` |
| `PUBLIC_CANON_AUTH_ISSUER` | | `https://auth.backend.coolify.cyberdynecorp.ai`, with no trailing slash, exactly as the discovery document's `issuer` gives it. The endpoints are read from discovery (B2, resolved) |
| `PUBLIC_CANON_AUTH_CLIENT_ID` | | `cyb_5UIdba7PWtBo1MmH` |
| `PUBLIC_CANON_AUTH_AUDIENCE` | | `cybercanon` — the same string as `CANON_AUTH_AUDIENCE`, or the API refuses every credential this application obtains |

`PUBLIC_` is the prefix the browser build carries: none of these is a secret and
none may become one. There is no client-secret variable and there could not be.
The redirect address is **not** configured — it is the origin plus `/signed-in`.

Optional and server-only: `CANON_AUTH_POST_LOGOUT_REDIRECT=true` once the
post-logout URIs of §1.2 are registered, and `CANON_AUTH_INTERNAL_URL` only if
the `web` container must reach CyberdyneAuth at another address than the public
one. Leave it unset here.

### `postgres` and `minio`

Managed applications. Their credentials reach `api` as `CANON_DATABASE_URL` and
`CANON_OBJECT_STORE_URL`. Both carry persistent volumes and neither is backed
up, deliberately — see [`../docs/recovery.md`](../docs/recovery.md).

---

## 3. Standing pre-production up (task 8.4)

The Migration Plan's order, with what to confirm at each numbered step. Run it
from the artifacts already built and recorded — `just release-promotion` is the
gate that says an environment is running what was recorded rather than a
rebuild.

**1. Create the PostgreSQL and MinIO applications with their volumes.**
Record their connection settings as `CANON_DATABASE_URL` and
`CANON_OBJECT_STORE_URL` on the `api` application.
*Confirm:* both applications report healthy, and both volumes are mounted at the
paths [`coolify.yaml`](coolify.yaml) declares.

**2. Create the working-copy volume and the deploy credential; run the initial
clone.**
*Confirm:* `/status` reports a revision and a fetch time for the project. The
clone is done by the service itself on start — it is re-entrant, so a volume
that already holds a copy is adopted rather than re-obtained.

**3. Run the migration release command against the empty database.**
```
python -m cybercanon.api.migrate
python -m cybercanon.api.migrate --schema-version
```
*Confirm:* the second command reports the target version. A non-zero exit from
the first aborts the release; no instance of the new version starts and the
previous one keeps serving.

**4. Deploy the API.**
*Confirm:* `/healthz` answers, `/readyz` answers ready, `/status` refuses an
unauthenticated request. Then the sharper half of the step — **deliberately
misconfigure the model gateway and the identity provider and confirm `/readyz`
is still ready**, with both named as degraded on `/status`. Readiness depends
only on what this service owns; another team's outage may not fail a CyberCanon
deploy.

**5. Build the index for each project.**
```
python -m cybercanon.api.recover /data/worktrees/<project>
```
*Confirm:* `/status` reports the index in sync, naming the same revision as the
working copy, **and `/v1/projects/<CANON_PROJECT>/assets` returns rows rather
than `total: 0`**. The second half is what B3 was: a rebuild can report assets
indexed and still leave every listing empty if the rows went in under another
name. Name the copy at the path the volume keeps it at — `/data/worktrees/` plus
`CANON_PROJECT` — and the two agree by construction.

**6. Deploy the web application.**
*Confirm:* it becomes ready **with the API stopped** — readiness is process-only
(D10) — and that a page then renders an explicit unavailable state rather than
an error.

**7. Register the git webhook.**
Point it at the repository notification endpoint with `CANON_WEBHOOK_SECRET` as
the signing secret.
*Confirm:* a push advances the working-copy revision on `/status`, and that both
the webhook and the schedule update `WorkingCopyStatus` identically.

**8. Sign in.** Not a numbered step in the plan, because the plan predates the
client existing. Do it anyway before calling the environment stood up: open the
application, sign in, and confirm the frame names the person and a project
screen renders. B2 is resolved. Also confirm that signing out and signing in
again shows CyberdyneAuth's login page rather than signing you straight back in.

Afterwards, the drills (`just drill`) run against this environment, and
`just drill-check` is the release pipeline's gate over their log.

---

## 4. Task 8.2 — the model endpoint

Set `CANON_LLM_ENABLED`, `CANON_LLM_BASE_URL`, `CANON_LLM_API_KEY`,
`CANON_LLM_MODEL` and `CANON_LLM_VISION_MODEL` per §2 and redeploy — a value
change is a restart, never a rebuild.

*Confirm:*

1. `/status` reports `language_model` as `available` rather than
   `CANON_LLM_ENABLED is off`;
2. ingest a concept image and confirm a description comes back;
3. **and the half the task is actually about** — confirm no egress to a
   third-party endpoint. `CANON_LLM_BASE_URL` is an internal Coolify address, so
   the check is that the `api` application's egress shows traffic to
   `amini.backend…` and to nothing outside the estate for the duration of the
   description.

The opt-in suite `tests/integration/test_model_endpoint.py` exercises the
gateway from a machine that can reach it; it skips with `CANON_LLM_ENABLED`
unset, which is the default everywhere, and it says so per test rather than
reporting green over nothing.

---

## 5. What the end-to-end stack now proves, and what it does not

`deploy/e2e/compose.yaml` runs a real CyberdyneAuth —
[`issuer.Dockerfile`](e2e/issuer.Dockerfile) over `tools/canon_issuer`, the same
issuer the port-conformance, integration and BDD layers mint against. Before
that, `CANON_AUTH_KEY_SET_URL` named an address on the `api` that **nothing
served**: the catch-all refuses any path carrying no surface version, the key set
retrieval answered 400, and no credential could ever verify. That is why every
browser assertion this project had ever made was made about a signed-out page.

`tests/e2e/test_web_signed_in.py` now drives the whole flow in a real browser —
the button, the redirect out, the code exchange, the credential, the screen.

Since B2 was fixed, the application has no hard-coded paths: the stack's issuer
is found through its discovery document, as CyberdyneAuth is. The fake issuer
no longer sends `Access-Control-Allow-Origin: *`, so a browser that went back to
calling the issuer cross-origin fails here as it would in production. The web
unit suite (`tests/auth-relay.test.ts`) pins discovery against a document with
CyberdyneAuth's own `/api/v1/auth/oauth2/…` paths.
