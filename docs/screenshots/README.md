# The neo-brutal interface, screen by screen

Captured at **laptop width (1280 × 800, 2× device pixel ratio)** from the
end-to-end stack — `deploy/e2e/compose.yaml`, the real API in front of a real
PostgreSQL, serving the worked example in `examples/ronin`. They exist so the
restyle can be reviewed without bringing that stack up.

`openspec/project.md` ("Visual language — neo-brutalism") is the decision these
render; `apps/cybercanon/web/src/lib/styles/tokens.css` is every value in them.

## What was signed in, and how

01 through 14 were **re-captured from the stack as it now ships**, with no
identity provider bolted on from the host. `deploy/e2e/compose.yaml` runs
CyberdyneAuth as a service of its own — `deploy/e2e/issuer.Dockerfile` over
`tools/canon_issuer`, the same issuer the port-conformance, integration and BDD
layers mint against — and the browser completed a real authorization-code
exchange with a real proof key against it. The API verified the credential
against the published key set, resolved `auth|rafa`, and answered from the real
index.

Until that service existed, `CANON_AUTH_KEY_SET_URL` named an address on the
`api` that **nothing served**: the catch-all refuses any path carrying no
surface version, the retrieval answered 400, no credential could ever verify,
and the stack served no authenticated screen at all. That is why the earlier set
needed an issuer on the host, and why `tests/e2e/` could only assert what a
signed-out browser sees. It now asserts the signed-in half too
(`tests/e2e/test_web_signed_in.py`).

15 through 20 are the earlier captures, unchanged: they are the screens that
need something the seeded project cannot produce — a substituted API answer, an
unmapped identity, an expired session.

**One step is not automatic.** The index is rebuilt from the working copy by an
operator command rather than by the service, so these were taken after running
the rebuild against the running stack, keyed by the project the surface serves.
It is `python -m cybercanon.api.recover` against the copy under the stack's
working-copy volume: the directory the copy is kept in is the name the surface
serves it at, which is what `deploy/go-live.md` §0 (B3) records and what the
entry point now keys rows by.

| | Screen | Credential | Data |
|---|---|---|---|
| 01 | Sign-in | none | live |
| 02 | Projects, signed out | none | live |
| 03 | Asset browser, signed out → `forbidden` | none | live |
| 04 | Projects | signed in | live |
| 05 | Asset browser | signed in | live |
| 06 | Search: the exact group | signed in | live |
| 07 | Asset browser, filtered | signed in | live |
| 08 | `empty` — the filters excluded every match | signed in | live |
| 09 | `empty` — nothing matched | signed in | live |
| 10 | Asset overview | signed in | live |
| 11 | Model sheet | signed in | live |
| 12 | 3D viewer | signed in | live |
| 13 | `not-found` | signed in | live |
| 14 | Triage pass | signed in | live |
| 15 | Sign-in callback → `degraded` | none | live |
| 16 | `failed` | signed in | **API answer substituted** |
| 17 | Model sheet at tablet width (834) | signed in | live |
| 18 | How a result matched, and the approximate group | signed in | **API answer substituted** |
| 19 | A person with no git identity, warned before they write | signed in, unmapped | live |
| 20 | An expired session | signed in, expired | live |

**The two substitutions, and why.** Both are answers the *API* gives, not
screens the application invents, and the seeded project cannot produce either:

* **16** — the stack has no way to return a conflict, so one `409` was returned
  to the browser for the listing call. `failed` is the sixth member of the
  closed route-state set and the only one not otherwise reachable here.
* **18** — the worked example has one asset, no aliases in the index and no
  CyberArche workspace linked, so a search over it can show neither *how* a
  result matched nor the approximate group. The search response was replaced
  with one that carries both.

## What the set covers

All six members of the closed route-state set (D6) appear as six distinct
screens: `content` (05), `empty` (08, 09), `forbidden` (03), `not-found` (13),
`degraded` (01, 15) and `failed` (16).

Every authenticated screen carries the acting identity in the frame, which is
visible in the top right of 04 through 20.

## What was removed

`sign-in.png`, `browser.png`, `asset.png`, `sheet.png`, `viewer.png` and
`triage.png` were captured before the restyle landed — serif type on white, soft
radii, hairline borders, browser-default links — and nothing referenced them.
They are the same six screens this set carries, in the look this change
replaced, so leaving them in a directory with no naming convention to tell the
two apart would have made this folder a worse answer to *"what does it look
like"* than no folder at all. They are in the history at `a91368c` if a
before-and-after is ever wanted.

## Reproducing them

Bring the stack up (`just test-e2e` does it, or `docker compose --file
deploy/e2e/compose.yaml up --wait --build`), rebuild the index against it, then
drive a browser through `/sign-in` — the application does the rest, because the
stack now contains an issuer that answers.

They are still not a recipe in the justfile, for a smaller reason than before:
the index step is an operator command rather than something the service does at
start, and a recipe that silently depended on somebody having run a command by
hand would be a recipe that misleads. `tests/e2e/` is the automated claim about these screens;
these images are the reviewable one.
