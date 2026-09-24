---
name: cybercanon-verify
description: Verify a CyberCanon production deployment end to end - /status and index freshness, the worker's service-token admission, refusal reasons in the log, a real browser sign-in against CyberdyneAuth, and (only when asked) a real annotation write-back that commits to the content repository. Use after every deploy, when asked "is CyberCanon working?", or to reproduce a production bug.
---

# Verifying CyberCanon in production

Run from the repository root. The script never prints a credential or a raw
token (tokens are decoded to their claims).

```bash
V=.claude/skills/cybercanon-verify/scripts/verify_prod.py
python3 $V status        # /status for ronin: working copy revision, fetch time, index
python3 $V wait-index    # blocks (≤5 min) until index.in_sync — the post-deploy gate
python3 $V worker        # worker token claims, then an authenticated read (expect 200)
python3 $V refusal       # junk bearer → 401 with the single undisclosing sentence
python3 .claude/skills/cybercanon-deploy/scripts/canon_coolify.py logs api --grep '"status": 401'
                         # → the same request logged with a non-null "reason"
```

`status`, `wait-index` and `worker` mint a client-credentials token from the
worker credential stored on the api app in Coolify (needs
`COOLIFY_CYBERDYNE_URL` / `COOLIFY_CYBERDYNE_TOKEN`).

## As a person (Playwright)

Needs `playwright` for Python with chromium, and the smoke account in the
environment — **never in a file, commit or PR**:

```bash
export CANON_SMOKE_USER=…  CANON_SMOKE_PASSWORD=…   # ask the user; the test account holds all four roles
python3 $V browser
```

Expect `'Signed in as': True`, `'no git identity': False`,
`'API is not answering': False`, and an access token with `aud=cybercanon`,
`type=access` and roles prefixed `cyb_5UIdba7PWtBo1MmH:`.

The 401s from `auth.backend…/api/v1/users/me` and `/auth/refresh` during sign-in
are CyberdyneAuth's login page probing for an existing session — expected.

## A real write-back (only when the user asks)

```bash
python3 $V write --confirm --label <unique-label>
```

Creates annotation `an_smoke_<label>` on `mech_scout`'s front concept view,
which **commits to CyberdyneCorp/ronin**. Use a new label every time — reusing
one replays the cached response (idempotency), and a key first used by a refused
request answers 409. Then check the commit author:

```bash
gh api repos/CyberdyneCorp/ronin/commits -q '.[0]|.commit.author.name+" <"+.commit.author.email+">"'
```

Expect the `display_name` from `.canon/actors.yaml` (e.g. "Leo Test"), not a
UUID. Expected latency ≈ 2.5–3 s including the push to GitHub (budget 20 s).

## Known state (update when it changes)

* Since web commit `6964541`, the Model sheet reads current reference images
  from repository view revisions and groups path/slot aliases into one card.
  `mech_scout` showed both images in production on 2026-09-24.
* Since web commit `6964541`, the viewer loads Draco-compressed previews.
  `mech_scout` rendered its model in production on 2026-09-24.
* A concept-view upload race exists (two concurrent ingestions can both commit).

Report anything new to the cannon-team session with the request id and the
redacted log line.
