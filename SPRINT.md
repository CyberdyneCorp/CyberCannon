# Current sprint brief — S6 (M2, `add-web-backend` groups 1–4)

This file is the self-contained briefing for a scheduled or fresh agent session.
Read it, then read what it points at, then implement.

## Read first, in this order

1. `openspec/project.md` — binding architecture, testing strategy, tooling, and the
   **"Gate Decisions (G1, G2, G4)"** section, which resolves the open questions this
   sprint depends on. Do not re-decide them.
2. `ROADMAP.md` — where S6 sits and what it gates.
3. `openspec/changes/add-web-backend/proposal.md`, `design.md` (decisions are numbered
   D1, D2, …), and **every** file under its `specs/`.
4. The existing code under `libs/cybercanon/`. Milestones M0 and M1 are complete and
   green (1361 tests). Match their conventions; do not reinvent what exists.

## Scope

Implement **only task groups 1, 2, 3 and 4** of
`openspec/changes/add-web-backend/tasks.md` — 24 tasks:

1. Service skeleton and the layering contract for a third adapter
2. Domain — tenancy, roles, authorization policy
3. Domain — asset requests
4. Application — outcome vocabulary, ports and use cases

**Do not start group 5 or later.** Groups 5+ are later sprints.

## Environment

`uv` manages Python dependencies, `just` is the task runner. Install if missing — `uv`
via the Astral installer, `just` via `uv tool install rust-just` — then `just setup`.
Node is required for the `just spec` recipe.

## Rules

1. **Never edit anything under `openspec/changes/*/specs/` or `openspec/specs/`.** The
   specs are frozen. If a spec is wrong, unimplementable, or contradicts another: stop
   that task, leave it unchecked, and say so in the pull request. Never change a spec to
   make code pass.
2. **Implement exactly those four groups.** If you believe existing M0/M1 code is wrong,
   report it rather than rewriting it.
3. **Follow the numbered design decisions.** State any deviation and the reason.
4. **Never mark a task done you did not verify.** An inflated count is worse than a low
   one — a previous agent correctly *unchecked* an over-claimed task, and that precedent
   stands.
5. Mark completed tasks `- [x]` in `tasks.md`, and remove the scenarios you close from
   `tests/bdd/pending.txt`.

## Architecture (violating these is a bug, not a style choice)

- `domain <- application <- adapters`. Inbound adapters never import outbound ones.
  **The domain imports only the standard library** — a custom `stdlib_only`
  import-linter contract enforces it and it does bite.
- PostgreSQL is a **rebuildable index**, never authoritative. Git is the source of truth.
- The HTTP surface is a thin adapter over the **same use cases** the CLI and the MCP
  server call. No second implementation of validation, compilation or lookup ranking.
- Authorization is domain policy; the adapter only translates claims and groups. The
  operation→role matrix is in `project.md` under Gate Decisions (G4).
- Identity comes from verified claims, never from a path, body or parameter.

## Testing

- Unit tests for domain and application — pure, no I/O.
- Port conformance suites run against the in-memory fake **and** the real adapter.
- BDD: write **step definitions** for the scenarios your code satisfies and remove those
  lines from `tests/bdd/pending.txt`. `.feature` files are generated from the specs —
  never hand-write or hand-edit one.

## Deliverable

1. `just check` must pass. Report its runtime and test count.
2. Work on a branch named `sprint/s6-web-backend`.
3. Open a **pull request** against `main` whose description states: tasks completed,
   tasks left unchecked **and why**, scenarios moved off the pending list, any deviation
   from a numbered design decision, and any spec problem found.
4. Do not merge the pull request.
