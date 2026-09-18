# mech_scout — Scout Mech

**Status:** modeling
**Also known as:** scout walker, mech scout
**Compiled from:** `characters/mech_scout/asset.yaml`

> Derived file — CyberCanon compiles it from `asset.yaml`. Edit the specification, not this file.
> It carries durable rules and currently open issues only; resolved and promoted threads live in git history.

## Concept — authored by art

- **Owner**: rafa
- **Silhouette rule**: One asymmetric shoulder reads as the front at 25 m.
- **Silhouette rule**: The head sits below the shoulder line; it never breaks the top edge.
- **Concept views**: concept/mech_scout_front.png, concept/mech_scout_three_quarter.png

## Design — authored by design

- **Owner**: dani
- **Role**: fast recon walker, no sustained fire
- **Read distance**: 25.0 m
- **Silhouette priority**: legs over torso
- **Scale reference**: 3.2 m at the shoulder
- **Team colour regions**: shoulder pauldron, calf plate

**Required attachment points** — the export is rejected without them:
- `SOCKET_muzzle_l`

**States:**
- `walk` — clip `A_mech_scout_walk` (30.0 fps, at least 0.1 s, root motion, loop closed)
- `fire` — clip `A_mech_scout_fire` (30.0 fps, at least 0.05 s, root motion)

## Engineering constraints — authored by engineering

_Effective values: project defaults with the asset's own declarations taking precedence._

- **Owner**: leo
- **Triangle budget**: 12000
- **LOD triangle budgets**: 12000, 6000, 2000
- **Up axis**: Y
- **Unit scale**: 1.0
- **Object naming**: `SM_{asset}_LOD{n}`
- **Pivot**: feet centre, origin at world zero
- **Collider**: convex hull, 12 faces
- **Texture size**: 2048
- **Texture sets**: 1
- **Texture channels**: base_color, normal, orm
- **Skeleton**: SK_MechScout
- **Bone budget**: 64
- **Clip naming**: `A_{asset}_{state}`
- **Clip frame rate**: 30.0

## Open issues

_Open only. A resolved or promoted thread is not context; it is history._

- **[art-direction]** on `SM_mech_scout_LOD0` (dani): The pauldron still reads as a backpack from behind at 25 m.

## Links

- **Source file**: `art/source/mech_scout.blend`
- **Engine path**: `Content/Ronin/Characters/MechScout`
- **Design document**: https://arche.cyberdynecorp.ai/d/ronin-recon-roster

