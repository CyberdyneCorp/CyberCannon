# Proposal

## Why

The first sign-in against the real CyberdyneAuth (client `cyb_5UIdba7PWtBo1MmH`)
failed at every step after the button:

1. **The endpoints were guessed.** `config.ts` built the authorization and token
   addresses from fixed paths (`/authorize`, `/oauth/token`). CyberdyneAuth serves
   them at `/api/v1/auth/oauth2/…`, so "Sign in with CyberdyneAuth" landed on a
   404 (`deploy/go-live.md` B2).
2. **Correct paths were not enough.** CyberdyneAuth sends no
   `Access-Control-Allow-Origin` for the application's origin. The browser could
   read neither the discovery document nor the token response, and the code
   exchange failed with *"Failed to fetch"*. The e2e issuer hid this because it
   answered `Access-Control-Allow-Origin: *`.
3. **Sessions died after fifteen minutes.** The default scope requested no
   `offline_access`, and the refresh token was thrown away when one came back,
   so every session lapsed with its 15-minute access token.
4. **Sign-out was local only.** The identity service's own session survived, so
   the next person on a shared machine was signed straight back in as the
   previous one. `web-session` exists to prevent exactly that.
5. **The frame printed a UUID.** CyberdyneAuth's access token carries no `name`
   or `email`. The person's email is in the id token, which was discarded.
6. **An id token could have been the API credential.** When a response had no
   access token, the code fell back to the id token. The id token's audience is
   the client, not the API.

## What Changes

- The web **server** reads `<issuer>/.well-known/openid-configuration`, checks
  that its `issuer` matches the configured one, caches it, and serves three
  same-origin relays:
  - `GET /auth/authorize` redirects to the discovered authorization endpoint;
  - `POST /auth/token` forwards the `authorization_code` and `refresh_token`
    grants to the discovered token endpoint, with the configured client id;
  - `GET /auth/end-session` redirects to the discovered end-session endpoint.

  The relay stays a public client: the proof key stays in the browser, it adds
  no secret, and it keeps nothing. If discovery fails, sign-in reports that it
  is unavailable (`temporarily_unavailable`) instead of crashing.
- The default scope becomes `openid profile email offline_access roles`.
- The session keeps the whole credential (access, refresh and id token) in the
  tab's session storage. It renews shortly before the access token lapses and
  replaces the rotated refresh token. A refused renewal falls back to D5's
  in-place re-authentication.
- Sign-out clears local state, then goes to the identity service's end-session
  endpoint with `client_id` and `id_token_hint`. `post_logout_redirect_uri` is
  sent only when `CANON_AUTH_POST_LOGOUT_REDIRECT` says the URI is registered.
- The acting identity is named from the id token (`name`, else `email`), then
  the access token, then the subject.
- Only the access token is ever presented to the API.
- The e2e issuer stops sending `Access-Control-Allow-Origin: *`. The web
  container reaches the issuer over the compose network through
  `CANON_AUTH_INTERNAL_URL`.
- A signed-in frame whose API never answers renders with no projects instead of
  a 500. The layout's own comment already promised this.

## Out of scope

- How the API reads the role claim (`roles` arrives as
  `cyb_5UIdba7PWtBo1MmH:<role>`, not `groups`) and the missing `projects`
  entitlement claim. Both belong to the API's claim reading, which another team
  owns, and both are reported in `deploy/go-live.md` B4.
- Registering the post-logout redirect URIs with CyberdyneAuth. That is a human
  step, recorded in `deploy/go-live.md` §1.2.
- The unmapped-git-identity warning. CyberdyneAuth emits no `git_emails`, so
  the warning shows for everyone until `http-api` exposes the `actors.yaml`
  mapping. That gap is already recorded in `identity.ts`.

## Impact

- Affected specs: `web-session` (ADDED requirements). The base `web-session`
  and `auth-integration` specs are still unarchived deltas in
  `add-web-app-shell` and `add-web-backend`, so a MODIFIED delta is not yet
  possible.
- The `auth-integration` rule that the surface SHALL NOT *"issue or hold a
  long-lived credential on the person's behalf"* is about the API. The refresh
  token is issued by the identity service to the person's browser and held only
  in that tab's session storage. The requirement below states this explicitly.
- Affected code: `apps/cybercanon/web` (`lib/config.ts`, `lib/session/*`,
  `lib/server/identity.ts`, `routes/auth/*`, `routes/+layout.ts`, `SessionBar`),
  `tools/canon_issuer/service.py`, `deploy/e2e/compose.yaml`,
  `deploy/coolify.yaml`, and the deploy documents.
