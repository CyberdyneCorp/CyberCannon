---
name: cybercanon-content-repo
description: Maintain the game content repository the hosted CyberCanon serves (CyberdyneCorp/ronin) - seeding art with `just seed`, validating exports before pushing, mapping people in .canon/actors.yaml, keeping canon's local files out of git, and rotating the repository credential. Use when adding or changing content in ronin, when a person cannot write ("no entry in .canon/actors.yaml"), or when the API reports the repository credential refused.
---

# The content repository (ronin)

The hosted API serves **one** project, `ronin`, from the private repository
`github.com/CyberdyneCorp/ronin`, branch `main` (`CANON_PROJECT=ronin`). The API
fetches it every 60 s and **commits back to it**: annotations, promotions,
validation results (authored as the person, or `canon automation` for the
background pass). Never point the API at this tool's own repository.

Work in a scratch clone, never inside the CyberCannon checkout:

```bash
gh repo clone CyberdyneCorp/ronin "$TMP/ronin" && cd "$TMP/ronin" && git pull --ff-only
```

## Adding art

Binaries never go into CyberCannon's history. `just seed` generates the
example's export and concept views **outside** the tool repository:

```bash
just seed "$TMP/ronin-content"            # from the CyberCannon checkout
cp "$TMP/ronin-content"/characters/mech_scout/exports/*.glb  "$TMP/ronin/characters/mech_scout/exports/"
cp "$TMP/ronin-content"/characters/mech_scout/concept/*.png  "$TMP/ronin/characters/mech_scout/concept/"
```

Copy only the generated binaries: `asset.yaml` in ronin carries annotations the
API has written, and the example's copy would erase them.

Validate before pushing, from inside the clone:

```bash
uv run --project <CyberCannon checkout> --locked canon validate characters/mech_scout/exports/SM_mech_scout_LOD0.glb
```

Expect `no violations`. Commit only the named files (`git add <paths>`, not
`-A`) and push. The API picks it up on the next fetch: the background pass
validates the export (a `canon automation` commit appears) and rebuilds the
index — confirm with `verify_prod.py wait-index` (`cybercanon-verify` skill).

## Letting a person write

A write is refused (`actor.unmapped`) unless the person's CyberdyneAuth subject
has an entry with a real email in `.canon/actors.yaml`:

```yaml
schema_version: 1
actors:
  - subject: <CyberdyneAuth sub — a UUID, from the decoded access token>
    display_name: <shown as the git author name>
    emails:
      - <git author email>
```

`default_role` is **not** a grant — roles come only from the token's `roles`
claim (granted on client `cyb_5UIdba7PWtBo1MmH` by the team-cyberauth session).
Reading needs membership of the deployment's organisation plus at least one
role on that client. Asset owners named in `asset.yaml` with no actors entry
show as "(unmapped)"; that is accurate, do not invent bindings.

## canon's local files

`canon validate` writes `.canon/index.sqlite`, `queries.log` and
`reports.ndjson` into the working tree. ronin ignores them through
`.canon/.gitignore`; keep that file in any new content repository.

## The repository credential

`CANON_REPOSITORY_URL` embeds the token
(`https://x-access-token:<token>@github.com/CyberdyneCorp/ronin.git`) and
`CANON_REPOSITORY_CREDENTIAL` holds the same token so it is redacted from logs.
Prefer a fine-grained token scoped to ronin with Contents read/write. To rotate:
set both through the bulk env endpoint (`cybercanon-deploy` skill), redeploy the
api, check `verify_prod.py status` shows a fresh `last_fetch_at`. A refused
credential surfaces as "the configured repository credential was refused by the
remote", and a git error never names the repository (the URL is a secret).

No GitHub webhook is configured: a raw GitHub webhook cannot authenticate against
`/hooks/repository`, so the 60 s fetch is the only refresh.
