# The neo-brutal interface, screen by screen

Captured at **laptop width (1280 × 800, 2× device pixel ratio)** from the
end-to-end stack — `deploy/e2e/compose.yaml`, the real API in front of a real
PostgreSQL, serving the worked example in `examples/ronin`. They exist so the
restyle can be reviewed without bringing that stack up.

`openspec/project.md` ("Visual language — neo-brutalism") is the decision these
render; `apps/cybercanon/web/src/lib/styles/tokens.css` is every value in them.

## What was signed in, and what could not be

The e2e stack configures `CANON_AUTH_ISSUER` and `CANON_AUTH_KEY_SET_URL` at an
address **nothing in this repository implements**, so the stack as it ships
serves no authenticated screen: every asset surface answers `401`, and the
browser lands on `forbidden`. That is why the suite in `tests/e2e/` asserts only
what a signed-out browser can see.

For these captures the stack was pointed at a key set that does answer —
`tools/canon_issuer`'s `FakeIssuer`, which signs with real RSA keys, served over
HTTP on the host — so the API verified a real credential and returned real rows
from the real index. **The application, its components and its CSS are the
running build in every image below.** Nothing was mocked in the browser except
where a caption says so.

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

The captures are not a recipe in the justfile: they need an identity provider
the deployment does not have, and a recipe that only works with one bolted on is
a recipe that misleads. `tests/e2e/` is the automated claim about these screens;
these images are the reviewable one.
