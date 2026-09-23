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

`apps/cybercanon/web/src/lib/config.ts` builds both endpoints from the issuer
with **fixed paths**:

```ts
export const AUTHORIZE_PATH = '/authorize';
export const TOKEN_PATH = '/oauth/token';
```

Those are `tools/canon_issuer`'s paths. CyberdyneAuth publishes:

| | Published | What the application asks for |
|---|---|---|
| authorization | `/api/v1/auth/oauth2/authorize` | `/authorize` → **404** |
| token | `/api/v1/auth/oauth2/token` | `/oauth/token` → **404** |

Both 404s were observed directly. **There is no value of
`PUBLIC_CANON_AUTH_ISSUER` that fixes this**: any prefix that makes `/authorize`
resolve leaves the token address wrong, because the two paths do not share a
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

### B3 — the documented index rebuild keys rows by the wrong project

`deploy/README.md` and `docs/recovery.md` both give the recovery as:

```
python -m cybercanon.api.recover /data/worktrees/<project>
```

`services/cybercanon/api/recover.py` calls `rebuild_index("")` and passes **no**
`project=`, so rows are keyed by the `name:` declared in the working copy's
`.canon/project.yaml`. The hosted surface reads rows keyed by `CANON_PROJECT`,
which `deploy/e2e/compose.yaml` is explicit is *"deliberately not derived from
the repository URL or from `.canon/project.yaml`, which disagree"*.

Observed end to end in the e2e stack: with `CANON_PROJECT=ronin` and
`name: Ronin`, the recovery reported *"rebuilt 1 project(s), 1 asset(s)"*, the
row landed under `Ronin`, and `/v1/projects/ronin/assets` answered `total: 0`
for ever after. `rebuild_index` **already takes** the `project=` parameter and
documents it as existing for exactly this reason:

> a hosted deployment serves this working copy at one name and must key every
> row by it

so the gap is in the entry point, not in the use case. Which name wins is a
decision for the person who owns the specification, which is why this is
reported rather than changed.

**This blocks Migration Plan step 5** (*"build the index for each project;
confirm `/status` reports it in sync"*) whenever `CANON_PROJECT` and the
declared name differ — including by case alone.

### B4 — the group and project claims are not in `claims_supported`

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
as `cyb_5UIdba7PWtBo1MmH:<role>` (prefixed with the client id) and carries no
`groups` and no `projects`. Mapping those is the API's claim reading, which
another team owns. It is not changed by the web fix.

`claims_supported` is advisory rather than exhaustive in OIDC, so this is an
**open question for registration (§1.3)** rather than a proven defect: the
answer is whatever the token actually carries, and the first correctly-audienced
token settles it. If the names differ, `ClaimNames` is the one place to change —
it is a value object, not configuration, because *"what a studio changes is the
group mapping"*.

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
and the query cache, the browser goes to `end_session_endpoint` with `client_id`
and `id_token_hint`. Without that, the next person on a shared machine was signed
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

### 1.3 The claims the token must carry

This is the half that decides whether anybody can read anything, and it is the
one question to settle with whoever administers CyberdyneAuth.

| Claim | Read by | What it decides | Absent means |
|---|---|---|---|
| `sub` | `actor_from` | the `ActorId` | the credential is **refused** (`NO_SUBJECT`) |
| `aud` | `Trust` | that this token was minted for *this* service | **refused** |
| `iss`, `exp` | `Trust` | issuer and validity | **refused** |
| `name` | `actor_from` | what the frame shows | the subject is shown instead. The web frame reads `name`, then `email`, from the **id token**, which is where CyberdyneAuth puts the email |
| `groups` | `roles_from` | which `Role`s the actor holds | no roles: every mutating operation refuses, naming the role |
| `projects` | `Actor.may_see` | which projects the actor is entitled to read | **nothing is readable** |
| `tenant` | `tenants_agree` | the organisation | no tenancy question is asked |
| `git_emails` | `git_emails_from` | commit attribution (D13) | `.canon/actors.yaml` answers next |

Ask for `groups` and `projects` by those names. If CyberdyneAuth emits them
under other names, say so in the reply to this document: `ClaimNames` in
`libs/cybercanon/adapters/outbound/auth/claims.py` is the single place that
changes, and it is eight fields.

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

### 1.5 `CANON_AUTH_GROUP_ROLES`

The mapping is configuration and names no group in code, so *"adding a mapping
is a configuration change rather than a deploy"*. The right-hand side must be a
`Role`; a value that is not one contributes nothing, because a configuration
mistake may only ever grant **less**.

The roles are `ART_DIRECTOR` and `ARTIST` (`cybercanon.domain.identity.Role`).
Write the studio's real group names on the left:

```
CANON_AUTH_GROUP_ROLES=cybercanon-art-directors=ART_DIRECTOR,cybercanon-artists=ARTIST
```

An unmapped group grants nothing and is **not** an error — which is what makes a
mapping mistake look like what it is rather than like an outage.

---

## 2. The worksheet

Thirty settings on `api`, four on `web`. This table is the same set as
[`README.md`](README.md)'s and as [`coolify.yaml`](coolify.yaml)'s — that is
asserted in both directions by `tests/tooling/test_deploy_documents.py` and
`just deploy-check`, so a variable missing here is a build failure and not a
surprise on the day.

**⛔ = cannot be known until the OAuth client of §1 exists.**

### `api` — the fifteen it refuses to start without

| Variable | | Value for pre-production |
|---|:--:|---|
| `CANON_PROJECT` | | `ronin` — **and it must equal the `name:` in that project's `.canon/project.yaml` until B3 is resolved** |
| `CANON_REPOSITORY_URL` | | the project's git remote, e.g. `https://git.cyberdynecorp.ai/cyberdyne/ronin.git` |
| `CANON_REPOSITORY_BRANCH` | | `main` |
| `CANON_REPOSITORY_CREDENTIAL` | 🔒 | a deploy credential with **write** access — write-backs commit and push |
| `CANON_FETCH_INTERVAL_S` | | `300`. The schedule is the guarantee; the webhook only shortens the wait |
| `CANON_WEBHOOK_SECRET` | 🔒 | generate one, and give the same string to the git host in step 7 |
| `CANON_AUTH_ISSUER` | | `https://auth.backend.coolify.cyberdynecorp.ai` — the `issuer` in the discovery document, character for character |
| `CANON_AUTH_AUDIENCE` | ⛔ | the audience registered in §1.1, expected `https://api.backend.coolify.cyberdynecorp.ai`; **confirm against a real token** |
| `CANON_AUTH_KEY_SET_URL` | | `https://auth.backend.coolify.cyberdynecorp.ai/.well-known/jwks.json` |
| `CANON_AUTH_GROUP_ROLES` | ⛔ | §1.5 — needs the group names a real token carries |
| `CANON_DATABASE_URL` | 🔒 | from the managed PostgreSQL application, created in step 1 |
| `CANON_OBJECT_STORE_URL` | | from the managed MinIO application, created in step 1 |
| `CANON_LINK_EXPIRY_S` | | `900` |
| `CANON_WRITE_BACK_TIMEOUT_S` | | `30` |
| `CANON_DRAIN_WINDOW_S` | | `60` — **must be greater than the line above**, or the service refuses to start naming both |

### `api` — the fifteen whose absence is a feature being off

| Variable | | Default | Value for pre-production |
|---|:--:|---|---|
| `CANON_AUTH_KEY_CACHE_TTL_S` | | 900 | leave unset. An identity-service outage then costs new sign-ins and nothing else |
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
| `PUBLIC_CANON_AUTH_AUDIENCE` | ⛔ | the same string as `CANON_AUTH_AUDIENCE`, or the API refuses every credential this application obtains |

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
working copy. ⚠️ **B3 applies here.** Check that
`/v1/projects/<CANON_PROJECT>/assets` returns rows rather than `total: 0`. If it
returns zero while the recovery reported assets, the index was keyed by the
declared name and not by the address — stop and resolve B3.

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
