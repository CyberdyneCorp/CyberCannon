# Tasks

## 1. Endpoints from discovery, through the application's own origin

- [x] 1.1 Read `<issuer>/.well-known/openid-configuration` on the web server, refuse a document whose `issuer` is not the configured one, and cache it; verify with a CyberdyneAuth-shaped fixture (`/api/v1/auth/oauth2/…`) that no path is guessed
- [x] 1.2 Serve `/auth/authorize`, `/auth/token` and `/auth/end-session`; verify the token relay forwards only the two browser grants, sets the client id, refuses another origin, and answers `502 temporarily_unavailable` when the issuer is unreachable
- [x] 1.3 Point the browser's configuration at those relays and delete `AUTHORIZE_PATH` and `TOKEN_PATH`; verify every configured address is on the application's origin
- [x] 1.4 Report an unreadable discovery document on `/signed-in` as sign-in unavailable, not as a crash or a refusal

## 2. Credential, renewal and sign-out

- [x] 2.1 Request `openid profile email offline_access roles` by default; verify the authorization request carries it
- [x] 2.2 Keep the access, refresh and id tokens from the token response, and require an access token; verify an id-token-only answer signs nobody in
- [x] 2.3 Renew with the refresh token shortly before the access token lapses, once at a time, replacing the rotated token; verify rotation, the single in-flight renewal, the `expired` fallback on refusal and no change on an outage
- [x] 2.4 Sign out of the identity service after the local sign-out, with `client_id` and `id_token_hint`, and a post-logout redirect only when configured
- [x] 2.5 Name the acting identity from the id token; verify with a CyberdyneAuth-shaped access token that carries no name or email
- [x] 2.6 Bound every request to the issuer with a timeout, fall back to the last good discovery document for up to a day, share one discovery read between concurrent callers, and compare the issuer exactly; verify a hung issuer answers `502`/outage and a trailing-slash issuer is refused
- [x] 2.7 On a refused access token, renew silently and re-send the write once before holding it; keep the refresh token on `expire()`, retry a renewal the issuer did not answer, and serialise renewals across tabs (Web Lock + `BroadcastChannel`); verify each
- [x] 2.8 Post the identity-token hint to `/auth/end-session` in the body, not the query string

## 3. Stack and documents

- [x] 3.1 Stop the e2e issuer from answering `Access-Control-Allow-Origin: *`, and give the web container `CANON_AUTH_INTERNAL_URL` and adapter-node's `ORIGIN` (the relay is a form POST, and SvelteKit checks its origin); verify `just test-e2e` signs in and out through the relay
- [x] 3.2 Declare the two optional server-only settings in `deploy/coolify.yaml`
- [x] 3.3 Mark B1 and B2 resolved in `deploy/go-live.md` and `DEPLOY.md`. Record the real client registration, scopes, CORS and post-logout URIs. Correct the issuer format in `deploy/README.md`
- [x] 3.4 Verify against the live CyberdyneAuth from `http://localhost:5173`: sign-in, refresh through the relay, sign-out ending the identity service's session
- [ ] 3.5 Register the post-logout redirect URIs for `cyb_5UIdba7PWtBo1MmH` (human step), then set `CANON_AUTH_POST_LOGOUT_REDIRECT=true` on `web`
