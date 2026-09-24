# CyberCanon — Roadmap

**Status:** 20 changes specified, M0–M3 implemented. 39 capabilities · 326 requirements ·
715 scenarios (578 executing, 137 pending) · **608 of 642 tasks**.
Detail lives in `openspec/changes/<change>/`. This file is the ordering, the slicing, and the reasoning behind both.

The current post-M3 asset workspace pass caps the desktop 3D viewer height,
keeps tools and discussion beside the work, and condenses asset facts without
changing the established visual language. Browser checks now cover saving and
reopening 2D strokes and 3D anchors across phone, tablet, laptop, and desktop widths.
The annotation workspace now names the draft placement, makes 2D pins accessible,
and lists model notes by part beside the 3D viewer.

---

## The principle that sets the order

> **Every milestone must be usable by someone without anyone else changing a habit.**

That is the whole sequencing argument. A tool requiring artists, designers and
programmers to adopt it simultaneously gets adopted by nobody — the adoption cliff.
So: programmers get value from a CLI that costs them nothing → their agents get value
from files that already exist → then artists are asked to open a web page, by which
time the spec files are there and have already proved useful.

The corollary is deliberate and uncomfortable: **the artist-facing UI — what people
picture when they hear "collaboration tool" — starts at sprint 17.**

---

## How sprints were sliced

- **Cap ~26 tasks per sprint**, average 21. Actual range 16–26.
- **Sliced along task-group boundaries**, never mid-group. A group is a coherent
  layer (domain, ports, adapters, a surface); splitting one leaves a sprint that
  cannot be demonstrated.
- **A sprint ends on something demonstrable** — not "half the adapters done".
- **Task counts are the size signal, not estimates.** There is no velocity data yet.
  Calibrate the cap after S1 and reflow; the slicing holds, only the width changes.

## Backend / frontend split — read this before staffing

| Track | Tasks | Share |
|---|---:|---:|
| Backend, domain, CLI, MCP, infrastructure | ~440 | **82%** |
| Frontend (SvelteKit application) | ~95 | **18%** |

**This is a backend-heavy product, and pretending otherwise would mis-staff it.**
A dedicated frontend team would sit idle for the first eight sprints and again
between S13 and S17.

Frontend work is **concentrated in two bursts**: S9–S13 (the application shell,
browser and session) and S17–S20 (the model sheet, then the 3D viewer). It cannot
start before S9, because it consumes an HTTP contract that does not exist until S8.

The honest staffing conclusion: **one team, not two tracks.** A frontend specialist
joins at S9 and, between the two bursts, works on adapters — which is also how the
`http-api` gaps get found by the person who will have to consume them.

---

## Sprint plan

| Sprint | Change · task groups | BE | FE | Total | Delivers | Gate/Milestone |
|---|---|---:|---:|---:|---|---|
| **S0** | `add-test-strategy` g1–5, g7 · `add-asset-spec-and-validator` g1 | 26 | 0 | **26** | **Foundation.** uv, justfile, import-linter, CI; the spec→`.feature` generator and both traceability gates. First run reports 657 pending scenarios, zero failures | |
| **S1** | `add-asset-spec-and-validator` g2–3 | 20 | 0 | **20** | Pure domain: the `asset.yaml` contract, validation rules over `MeshFacts` |  |
| **S2** | `add-asset-spec-and-validator` g4–5 | 19 | 0 | **19** | Ports, use cases, outbound adapters (git, trimesh, Draco preview) |  |
| **S3** | `add-asset-spec-and-validator` g6–7 · `add-mcp-read-server` g1 | 22 | 0 | **22** | **M0 — `canon` validates.** CLI, pre-commit hook, one real asset end to end | **M0** |
| **S4** | `add-mcp-read-server` g2–3 | 22 | 0 | **22** | Identity resolution, lookup, discipline lenses |  |
| **S5** | `add-mcp-read-server` g4–6 | 21 | 0 | **21** | **M1 — agents read the canon.** SQLite index, stdio MCP server, `where_is` | **M1** |
| **S6** | `add-web-backend` g1–4 | 24 | 0 | **24** | Tenancy, roles, authorization policy, the outcome vocabulary | G4 |
| **S7** | `add-web-backend` g5–7 | 21 | 0 | **21** | Persistent working copy, PostgreSQL index, MinIO mirror | G1 G2 |
| **S8** | `add-web-backend` g8–9 | 18 | 0 | **18** | CyberdyneAuth and the HTTP surface — **the contract the frontend consumes** |  |
| **S9** | `add-web-backend` g10–11 · `add-web-app-shell` g1 · `add-test-strategy` g6 | 17 | 7 | **24** | Requests end to end; **frontend starts**: shell, routing, closed route states |  |
| **S10** | `add-coolify-deployment` g1–2 · `add-web-app-shell` g2–3 | 13 | 12 | **25** | Fail-fast boot, health/readiness; typed client, query cache, session experience |  |
| **S11** | `add-coolify-deployment` g3–5 · `add-web-app-shell` g4 | 17 | 8 | **25** | Containers, migrations, volumes; asset browser and search |  |
| **S12** | `add-coolify-deployment` g6–8 · `add-web-app-shell` g5 | 19 | 4 | **23** | **M2 — it is deployed.** Zero-downtime rollover, recovery drills | **M2** |
| **S13** | `add-web-app-shell` g6–7 · `add-concept-ingestion` g1 | 8 | 8 | **16** | Asset page and shell acceptance; view and slot domain |  |
| **S14** | `add-concept-ingestion` g2–3 | 18 | 0 | **18** | Upload, attributed commit, thumbnails, mirroring |  |
| **S15** | `add-concept-ingestion` g4–7 | 21 | 0 | **21** | Revision history, the carry-or-orphan rule, freshness |  |
| **S16** | `add-model-sheet-2d` g1–2 | 20 | 0 | **20** | Annotation domain, threads, triage policy | G3 |
| **S17** | `add-model-sheet-2d` g3 · `add-model-sheet-2d` g4–6 | 5 | 20 | **25** | Write-back; **the shared `AnnotationViewModel`** and the 2D model sheet |  |
| **S18** | `add-viewer-3d` g1–3 · `add-viewer-3d` g4 | 15 | 6 | **21** | Anchor policy without geometry, viewer HTTP surface, three.js scene |  |
| **S19** | `add-viewer-3d` g5–7 | 0 | 18 | **18** | Anchor re-projection, orphans, pins over the reused ViewModel, counts |  |
| **S20** | `add-viewer-3d` g8–9 · `add-cyberarche-integration` g1–2 | 9 | 12 | **21** | **M3 — artists use it.** Animation playback; CyberArche port | **M3** |
| **S21** | `add-cyberarche-integration` g3–5 | 23 | 0 | **23** | Document linking, search routing, outbound adapter |  |
| **S22** | `add-cyberarche-integration` g6–7 · `add-derived-metadata` g1–2 | 21 | 0 | **21** | Compilation boundaries; OpenAI-compatible client |  |
| **S23** | `add-derived-metadata` g3–5 | 18 | 0 | **18** | Derived records, normalisation, boundary enforcement |  |
| **S24** | `add-derived-metadata` g6–7 · `add-mcp-writes` g1–2 | 24 | 0 | **24** | **M4 — integrations.** The `asset.yaml` writer; observations and write policy | **M4** |
| **S25** | `add-mcp-writes` g3–6 | 23 | 0 | **23** | **M5 — agents write.** Outbox, exactly two tools, visible agent authorship | **M5** |
**Totals:** 566 tasks · 26 sprints · max 26 · min 16 · avg 21.5

E2E setup (`add-test-strategy` g6) deliberately sits at **S9**, not S0 — there is no
surface to drive end to end until the frontend starts.

---

## Milestones

| | Ships at | What becomes usable | Who has to change a habit |
|---|---|---|---|
| **M0** | end S3 | `canon validate` as a pre-commit hook; `asset.yaml`; `art-spec.md` | nobody |
| **M1** | end S5 | `where_is` and the read surface for agents — Claude Code, Cursor, Blender | nobody |
| **M2** | end S12 | Hosted API on Coolify, auth, requests, the application shell | developers only |
| **M3** | end S20 | Concepts in, annotations, triage, 2D sheet, 3D viewer with animation | **everyone** |
| **M4** | end S24 | GDD links, delegated semantic search, suggested aliases | optional |
| **M5** | end S25 | `add_annotation`, `report_export` from agents | optional |

> **M0 + M1 are the whole product for programmers — three to five sprints.** If the
> project stopped at S5 it would already have paid for itself. Everything after is
> the collaboration half, and it costs four times as much.

---

## Dependency graph

```
S1 ──► add-asset-spec-and-validator ──► M0
         └─► add-mcp-read-server ──────► M1
               └─► add-web-backend ──────────────────► M2
                     ├─► add-coolify-deployment ──────┘
                     ├─► add-web-app-shell ──► add-model-sheet-2d ──► add-viewer-3d ──► M3
                     │      (needs the HTTP contract)        └─ reuses the ViewModel ─┘
                     ├─► add-concept-ingestion ──► (feeds the sheet)
                     ├─► add-cyberarche-integration ──► M4
                     ├─► add-derived-metadata ────────┘
                     └─► add-mcp-writes ──────────────► M5
```

---

## Gates — decide before the sprint that needs them

> **G1, G2 and G4 now have recorded working assumptions** in `openspec/project.md`
> ("Gate Decisions"). They were derived from binding decisions rather than chosen
> freely, and are overridable until M2 starts. **G3 now has a recorded working assumption** in `openspec/project.md`.

Each came out of adversarial review of the specs. Each is a data-model or
architecture call, and each is **cheaper now than after the code exists**.

| | Decision | Needed by | Why it is expensive later |
|---|---|---|---|
| **G1** | Who runs validation server-side, how the preview reaches MinIO, and how multi-GB exports live in a per-project working copy (Git LFS?) | **S7** | `viewer-3d` loads "the preview produced by the validation run" and `asset-lookup` returns "the most recent validated export" — neither exists on the server. Deciding late means retrofitting a job runner, a queue and an LFS story into a specified deployment. |
| **G2** | Where a validation outcome durably lives | **S7** | `report_export` delivers a verdict to "the destination"; `hosted-repository` requires that no write reach only the index. A reported outcome cannot be rebuilt from the repo, yet `where_is` depends on it. |
| **G3** | Asset creation, spec editing, and which status transitions are legal and by whom | **S16** | The only specified way to create an `asset.yaml` today is an image upload. `concept-ingestion` says a status change "remains a separate explicit human action" — an action specified nowhere. |
| **G4** | The role vocabulary and the operation→role matrix | **S6** | Five capabilities reference "the defined role set", "the art director role", "project write access". None defines them. Permissions are the last thing you want to redefine after commits are attributed and groups mapped in production. |

One smaller contradiction still awaits a call: whether a replaced concept view
carries its annotations or orphans them.

The other — an unmapped read-only actor raising an asset request that must become a
commit `hosted-repository` refuses — was **resolved in M2, in favour of the stricter
reading**: raising a request needs read access *and* a mapped git identity, the
refusal names the missing `.canon/actors.yaml` entry, and the reasoning is recorded
under "Gate Decisions (G4)" in `openspec/project.md`. The two specification deltas
still disagree on it, and one of them is wrong.

---

## Product boundary — what CyberCanon is not

Adjacent tools (SyncSketch and similar) are **review** tools: the unit of work is a
session, media goes in, humans draw on it together. CyberCanon's unit of work is the
**durable contract** — annotation exists to feed the two exits, promote or resolve.

Accepted deliberately: **no realtime session sync, no presentation mode, no
video/dailies review, no brush engine.** Each is months of work that makes CyberCanon
a worse version of a tool that already exists, while the `asset.yaml` contract — the
thing nothing else has — stays half-built. Whiteboard and long-form documents go to
CyberArche, the same reasoning that kept us from rebuilding an editor.

**Cheap wins worth adding after M3:** PDF summary of an asset's open issues (a second
renderer over data we hold), time-limited external share links for contractors, and
3D version compare (two previews side by side with the triangle delta).

## Deferred, with the trigger that would revive each

| Deferred | Revive when |
|---|---|
| pgvector / embeddings inside CyberCanon | the zero-result query log shows aliases failing, or ~5,000 assets |
| Formal asset dependency graph | `links:` demonstrably stops answering a real question |
| Mass-variation triage and voting | there is a volume of AI-generated variations to triage |
| AI auto-correction of meshes | never on current evidence — an agent rewriting geometry to satisfy a linter produces subtly broken assets |
| Full paint-over (brushes, layers) | it competes with Procreate; pins plus a scribble layer have to fail first |
| Hosted/multi-tenant MCP | someone outside the local-first model needs it, with its own threat model |

---

## Before sprint 1

Spend an afternoon with **Kitsu** (open source, free). It covers the review,
annotation and tracking half of this proposal. If Kitsu + `asset.yaml` + the validator
solves the actual problem, that is a far better starting point than a greenfield
platform — and M0 is deliberately built so it stays valuable either way.
