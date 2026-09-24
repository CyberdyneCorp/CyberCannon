---
name: cybercanon-deploy
description: Deploy CyberCanon (api, web) to the Cyberdyne Coolify instance and handle the project-specific parts the global coolify skill does not know - app UUIDs, which app a change needs, the migration pre-deploy caveats, the index rebuild, the env inventory and the worker allowlist rule. Use when asked to deploy, redeploy, roll out a merged PR, check the hosted state, or change CyberCanon's Coolify configuration.
---

# Deploying CyberCanon to Coolify

The generic Coolify workflow lives in the global `coolify` skill. This skill is
what is **particular to CyberCanon**. The design reference is
[`deploy/README.md`](../../../deploy/README.md) and the go-live worksheet is
[`deploy/go-live.md`](../../../deploy/go-live.md); read them for the *why*.

## The inventory

Instance `https://coolify.cyberdynecorp.ai` (`--server cyberdyne`, env
`COOLIFY_CYBERDYNE_URL` / `COOLIFY_CYBERDYNE_TOKEN`), project **CyberCanon**
(`wc3lkbltvd8pyeinb4kduvwq`), server `localhost`, environment `production`.

| Component | Coolify resource | UUID | Address |
|---|---|---|---|
| api | Dockerfile app, `deploy/api.Dockerfile`, port 8000 | `jzigiqhtqv2rl1zlthz9en8l` | https://api.backend.coolify.cyberdynecorp.ai |
| web | Dockerfile app, `deploy/web.Dockerfile`, port 5173 | `o5ry8gvl5iigfrkpbr3ogamj` | https://canon.backend.coolify.cyberdynecorp.ai |
| postgres | managed Postgres 16 (internal) | `gjib7dtmbdb5dfx4yyv9tpp1` | host = its UUID, db `canon` |
| minio | custom compose service (internal), bucket `cybercanon` | `tswe2tfmixoldt24kbrghtkb` | `minio-tswe2tfmixoldt24kbrghtkb:9000` |

Both apps build from `github.com/CyberdyneCorp/CyberCannon` branch `main`
(public repo, no webhook: **nothing auto-deploys on merge**). Never host the
`canon` CLI or the MCP server: `deploy/coolify.yaml` forbids it.

## Deploy

```bash
S=.claude/skills/cybercanon-deploy/scripts/canon_coolify.py
python3 $S state            # all four resources and their health
python3 $S deploy api       # or: deploy web — polls to the end, prints the key log lines
python3 $S logs api --grep '"status": 5'   # redacted; never echo raw logs
python3 $S envs api         # names only, never values
```

Deploy is a production action: confirm with the user first unless they have
told you to deploy in this conversation. If the auto-mode classifier blocks a
deploy, do not work around it — hand the user the command to run with `!`.

### Which app does a change need?

Diff the merged range, e.g. `git diff --stat <deployed-sha> origin/main`:

| Paths changed | Deploy |
|---|---|
| `libs/`, `services/`, `db/`, `pyproject.toml`, `uv.lock`, `deploy/api.Dockerfile` | **api** |
| `apps/cybercanon/web/`, `deploy/web.Dockerfile` | **web** |
| `tools/`, `tests/`, `openspec/`, docs, `justfile`, `scripts/` | nothing (not in either image) |

### Migrations: the pre-deploy caveat (read before every api deploy)

The api's pre-deploy command is `python -m cybercanon.api.migrate`. Coolify runs
it **inside the currently running container, i.e. the previous image**:

* **First deploy / api container not running** → Coolify logs
  `Pre-deployment command: No running containers found. Skipping.` and nothing
  is migrated; reads then 500 with `UndefinedTable`. Fix: deploy **again**, which
  migrates from the now-running container.
* **A release that adds a file under `db/migrations/`** → the old image's code
  runs, so the new migration is not applied. Deploy **twice** and check the
  second deploy's log shows `applied 000N_…`. Until a spec'd migrate job exists
  (open with cannon-team), there is a short window where new code serves before
  its migration.
* Normal release: the log line reads `applied nothing; N already present`.

Check for a migration before deploying: `git diff --stat <deployed-sha> origin/main -- db/`.

### Index

Since #17 the api's background pass builds the index whenever the indexed
revision differs from the served one. After a deploy, confirm with
`verify_prod.py wait-index` (the `cybercanon-verify` skill). If it is ever
needed by hand (`deploy/go-live.md` step 5): Coolify has no exec API, so set the
api's `pre_deployment_command` to
`sh -c "python -m cybercanon.api.migrate && python -m cybercanon.api.recover /data/worktrees/ronin"`,
deploy once, and **immediately restore** it to `python -m cybercanon.api.migrate`
— `recover` drops every index table (dismissals, idempotency keys included).

## Configuration rules

Change env through the Coolify API bulk endpoint, not the global CLI's
`app-env-set` (it can only update existing keys):
`PATCH /applications/{uuid}/envs/bulk` with
`{"data":[{"key":…,"value":…,"is_literal":true,"is_preview":false}]}`, then
redeploy that app. A value change is a restart, never a rebuild.

**api** — required (boot refuses naming any missing one): `CANON_PROJECT`
(`ronin`), `CANON_REPOSITORY_URL` (credential embedded as
`https://x-access-token:<token>@github.com/CyberdyneCorp/ronin.git`),
`CANON_REPOSITORY_BRANCH` (`main`), `CANON_REPOSITORY_CREDENTIAL` (same token;
used only for redaction), `CANON_FETCH_INTERVAL_S` (60), `CANON_WEBHOOK_SECRET`
(random; no GitHub webhook is configured — a raw GitHub hook cannot authenticate),
`CANON_AUTH_ISSUER` (`https://auth.backend.coolify.cyberdynecorp.ai`, **no
trailing slash**), `CANON_AUTH_AUDIENCE` (`cybercanon`), `CANON_AUTH_CLIENT_ID`
(`cyb_5UIdba7PWtBo1MmH`), `CANON_AUTH_ORG_ID`, `CANON_AUTH_KEY_SET_URL`
(`…/.well-known/jwks.json`), `CANON_AUTH_GROUP_ROLES`
(`art_director=ART_DIRECTOR,artist=ARTIST,designer=DESIGNER,engineer=ENGINEER`),
`CANON_DATABASE_URL`, `CANON_OBJECT_STORE_URL`
(`http://<user>:<pass>@minio-tswe2tfmixoldt24kbrghtkb:9000/cybercanon`),
`CANON_LINK_EXPIRY_S`, `CANON_WRITE_BACK_TIMEOUT_S` (20) **<**
`CANON_DRAIN_WINDOW_S` (30 — Coolify's stop timeout; the boot refuses an inverted pair).

**api — worker**: `CANON_WORKER_CLIENT_ID` (`cyb_9BGO5ArxAy5Um-FI`),
`CANON_WORKER_CLIENT_SECRET`, `CANON_AUTH_SERVICE_CLIENTS`. If the worker id is
set and is not **byte-identical** (case-sensitive) in the allowlist, the api
**refuses to start**. Unset allowlist = no service token admitted.

**web**: `PUBLIC_CANON_API_URL`, `PUBLIC_CANON_AUTH_ISSUER`,
`PUBLIC_CANON_AUTH_CLIENT_ID`, `PUBLIC_CANON_AUTH_AUDIENCE`,
`CANON_AUTH_POST_LOGOUT_REDIRECT=true`. Endpoints come from the issuer's
discovery document; no path is configured.

**Health checks**: api `/readyz` port 8000 host `127.0.0.1`; web `/readyz` port
5173 host `127.0.0.1`. The host must be `127.0.0.1`: busybox `wget` resolves
`localhost` to IPv6 and node only listens on IPv4.

## Who owns what

* Application code and specs: the **cannon-team** session. Report defects with
  file:line and prod evidence; do not patch their code from here.
* CyberdyneAuth (clients, roles, audiences): the **team-cyberauth** session.
* Answer their messages directly and ask them for missing facts before asking
  the user.

## After a deploy

Run the `cybercanon-verify` skill. At minimum: `state`, `wait-index`, and the
browser sign-in check.
