# CyberCanon — Project Context

## Purpose

CyberCanon is the **canon of a game project**: the single, versioned place where
what an asset *looks like* (art), what it *does* (design), and what it *must
respect technically* (engineering) are written down as one verifiable contract,
and where art, design and code argue about it against a shared artifact instead
of against taste.

It exists to kill three concrete costs in an indie studio:

1. **Art↔code misalignment.** There is no artifact saying what a concept *means*
   in verifiable terms, and no technical validation before someone spends three
   days modelling. This is the expensive one — it costs days.
2. **Discovery.** Developers do not know where the concept, the `.blend`, the
   export or the engine path for an asset live.
3. **Mechanical asset defects.** Scale, rotation, pivot, up-axis, naming and
   triangle budgets get fixed by hand, downstream, by the wrong person.

The product's real intellectual property is the **`asset.yaml` schema** and the
validator that enforces it. Everything else — web UI, MCP server, 3D viewer — is
a way to produce, read and enforce that file. Get the schema right and the rest
is plumbing; get it wrong and no interface saves it.

Day-to-day the binary is `canon` (`canon validate`, `canon where-is mech_scout`).
The product is **CyberCanon**. The *format* stays boring and self-explanatory
(`asset.yaml`, compiled `art-spec.md`) so it survives being read by a contractor,
a new hire, or an LLM that has never heard of this tool.

## The Golden Rule for the `design` block

> Every design field SHALL either **constrain art**, **constrain code**, or be
> **checkable by the validator**. A field that does none of the three is a wiki
> page, not a spec field.

The closed loop that justifies the whole system: design declares a socket
(`SOCKET_muzzle_l`) → art must place an empty with that name in Blender → the
validator reads `MeshFacts.empties` and fails the export if it is missing → code
never discovers at integration time that the VFX has nothing to attach to. A
designer's requirement becomes a mechanically enforced gate.

## Core Architectural Decision — Git is the source of truth

`asset.yaml` lives **in the game repository, next to the asset**. CyberCanon is a
renderer and editor over that repository, not a competing database. PostgreSQL
and MinIO are a **rebuildable cache/index and a blob mirror** — deleting them and
re-scanning the repo SHALL always be a valid recovery.

This decision is deliberate and it deletes features rather than adding them:

| Would-be feature | Why it disappears |
|---|---|
| Semantic versioning of art direction | Git already does it — diff, blame, branch, PR review. |
| Sync between the tool and the repo | There is nothing to sync. |
| "Invisible prompt injection" into agents | The file is already in the repo the agent reads. One line in `CLAUDE.md` is the whole integration. |

The `SpecStore` port keeps this reversible: `GitSpecStore` today, a
`PostgresSpecStore` later, with the domain untouched.

**Honesty about agent context:** there is no hook into the ChatGPT web UI. Design
for repo-file consumers (Claude Code, Cursor, the Blender agent) and accept
copy-paste for the rest.

## Annotations: durable anchoring and mandatory triage

- **Anchoring is the hard part, not the viewer.** A pin stored as triangle index
  + barycentric coordinates is precise and worthless the moment the mesh is
  re-exported — exactly when the feedback needs to survive. Anchors are
  therefore **dual**: the durable key is the *named part* (and optionally the
  bone); the point/normal are positioning hints, and the saved camera restores
  the viewing angle. A renamed or deleted part yields an **orphan** annotation,
  never a silently mis-placed one.
- **Annotations must not rot the context file.** Every annotation has exactly
  two exits: **promoted to a rule** (general and permanent → moves into
  `constraints` / `silhouette_rules`, annotation retired) or **resolved as an
  issue** (specific and transient → archived and excluded from the compiled
  spec). The compiled `art-spec.md` contains rules + open issues only; dead
  threads live in git history where no context window pays for them. This triage
  pass is the art director's actual job in the tool, and it is the loop that
  makes teams converge instead of just recording disagreements more neatly.

## Agents read constraints. Agents never write constraints.

The MCP write surface is minimal and proposal-shaped (`add_annotation`,
`report_export`). An agent flagging that a constraint is unreachable is valuable;
an agent *editing* the constraint so its output passes is how trust in the system
dies in week two.

## The validator SHALL never require identity

`canon validate` reads a file and returns violations — no network, no CyberAuth,
no token. If it needs the auth service, then the day auth is down or the artist
is off-VPN she cannot commit, and the tool becomes the enemy. Only *reporting* a
result to the server needs identity, and that part may fail silently and retry.

Its second job is social: it depersonalises feedback. The linter rejects the
file; the programmer does not reject the artist.

## Tech Stack

- **Backend** — Python 3.12+, FastAPI (inbound HTTP), FastMCP (inbound MCP,
  stdio for local use), Typer (inbound CLI), Hexagonal Architecture. Package
  namespace `cybercanon.<context>.<layer>`. Environment and dependencies managed
  by **`uv`** (committed `uv.lock`); every operation runs through a **`just`**
  recipe.
- **Persistence** — Git working copy via `SpecStore` (source of truth);
  PostgreSQL as rebuildable index/cache and FTS; MinIO (S3 API) for blobs —
  views, exports, decimated preview GLBs.
- **Mesh inspection** — `trimesh`/`pygltflib` behind a `MeshInspector` port
  (swappable for `bpy` later).
- **Frontend** — Svelte 5 (runes) + SvelteKit + TypeScript, selective MVVM,
  `three.js` for the 3D viewer. UI built on
  `@cyberdynecorp/svelte-ui-core` + `@cyberdynecorp/svelte-ui-foundation`.
- **Auth** — CyberdyneAuth (OIDC/OAuth2, JWKS-verified JWT) behind an
  `IdentityProvider` port.
- **LLM** — **OpenAI-compatible Chat Completions API only**, behind `LLMPort` and
  `VisionPort`. Endpoint, key and model names come from environment variables, so
  the same build points at OpenAI, at the on-prem AminiLLM/LiteLLM gateway, or at
  any compatible proxy without a code change. No provider SDK is imported outside
  the adapter.

## Developer Tooling — `uv` and `just`

Two tools, one rule: **there is exactly one way to run any operation, and it is a
`just` recipe.**

- **`uv`** manages the Python environment and dependencies. `uv.lock` is committed
  and authoritative: CI, the Coolify image build and a developer's machine resolve
  to identical versions. Dependencies are declared in `pyproject.toml` only —
  never installed ad hoc, never a bare `pip install`.
- **`just`** is the task runner. Every command a person or a pipeline runs — tests,
  lint, import contracts, complexity, migrations, `openspec validate`, serving the
  API, launching the MCP server, building the frontend — is a recipe in the root
  `justfile`. The frontend keeps `pnpm` for its own package management, wrapped by
  recipes so nobody has to remember which directory to be in.

**Why this is a convention and not a requirement:** it changes no observable
product behaviour, so it earns no spec. It is recorded here because it binds every
change, and because the alternative — a README full of commands that drift from
what CI actually runs — is the same class of failure as four validators: the
documented way and the real way diverge, and only CI knows.

The baseline recipe set, which changes extend rather than replace:

```
just setup        # uv sync + pnpm install
just check        # everything CI runs, in CI's order
just test         # pytest
just lint         # ruff
just imports      # import-linter — the domain <- application <- adapters contract
just complexity   # cognitive complexity against the domain targets
just spec         # openspec validate --all --strict
just migrate      # apply db/migrations
just api          # run the FastAPI service
just mcp          # run the FastMCP server over stdio
just web          # run the SvelteKit dev server
```

**`just check` is the contract.** CI runs that recipe and nothing else, so a green
local `just check` means a green pipeline. A check that exists in CI but not in the
recipe is a bug in the justfile.

## External Services (owned by us)

- **CyberdyneAuth** — identity provider. OIDC authorization-code + PKCE for the
  web app; device-code + OS keychain for the CLI/MCP; client-credentials for
  background work. The token format SHALL NOT leak into the core: the domain
  knows `Actor` and `Role`; the adapter translates claims and groups.
- **CyberArche** — the document platform. CyberCanon does **not** rebuild an
  editor: long-form GDD and design docs live in CyberArche and are *linked* from
  an asset/project. CyberArche's per-workspace RAG also serves semantic search
  over that prose; CyberCanon keeps only exact/FTS lookup over asset ids, names
  and aliases.
- **`@cyberdynecorp/svelte_components_library`** — the Cyberdyne design system
  (Svelte 5, dark-first). The frontend consumes it; it does not fork it.

## Architecture Conventions

### Backend — Hexagonal (mirrors CyberArche)

```
libs/cybercanon/domain/          # pure domain, zero I/O, no framework imports
libs/cybercanon/application/
    ports/                       # Protocols: spec_store, blob_store, mesh_inspector,
                                 #   search_index, identity_provider, notifier, doc_platform
    use_cases/                   # one folder per capability
    testing/                     # in-memory fakes
libs/cybercanon/adapters/
    inbound/  http/ mcp/ cli/    # FastAPI routers, FastMCP tools, Typer commands — thin
    outbound/ git/ postgres/ minio/ mesh/ auth/ arche/
    wiring/                      # single composition root -> Container
services/cybercanon/api/         # FastAPI deployable
services/cybercanon/mcp/         # FastMCP deployable (stdio only — never hosted)
services/cybercanon/cli/         # the `canon` binary
apps/cybercanon/web/             # SvelteKit frontend
db/migrations/                   # SQL migrations for the cache/index
```

Dependency rule: `domain <- application <- adapters`; inbound never imports
outbound. Enforced with import-linter.

**The boundary most implementations get wrong: mesh *rules* are domain; mesh
*reading* is a port.** `MeshInspector` returns a dumb `MeshFacts` value object
(triangles, objects, transforms_applied, unit_scale, up_axis, uv_sets,
materials, empties); the **domain** decides pass/fail against the spec. The
consequence is that the entire validator test suite runs over hand-built
`MeshFacts` with zero files on disk, and swapping `trimesh` for `bpy` touches one
adapter.

**One core, three inbound adapters.** The pre-commit validator the artist runs,
the `validate_export` the Blender agent calls, and the "Validate" button in the
web app are the *same use case*. Anything else produces "it passed on my machine
but the site says it failed" — precisely the trust-destroying bug this product
exists to prevent.

### Frontend — selective MVVM (Svelte 5 runes)

Runes are already a binding layer; a ViewModel per component is overhead. Use
MVVM where it pays: **one `AnnotationViewModel` serving both the 2D model sheet
and the 3D viewer**. The views' only job is to turn input into an `Anchor`
(`Sheet2D` → `Anchor2D{view,u,v}`, `Viewer3D` → `Anchor3D{part,point,normal,camera}`);
threads, filtering, triage, status are written once and tested with no DOM and no
GPU. That is what makes "support 2D and 3D" cost far less than twice.

Forms, asset browser and spec editor are plain Svelte components. Server state
lives in a query cache, not scattered across ViewModels.

- **View** = `*.svelte`; **ViewModel** = `*.svelte.ts` (module singleton +
  `createXxx()` factory for tests); **Model** = typed clients under `lib/api/`.
  Views never call the API directly.

## LLM Configuration — OpenAI-compatible, environment-driven

CyberCanon talks to language and vision models through the **OpenAI-compatible
Chat Completions API** and nothing else. One wire format, selected entirely by
environment:

| Variable | Meaning |
|---|---|
| `CANON_LLM_ENABLED` | Master switch. Default **false** — the system SHALL be fully usable with it off. |
| `CANON_LLM_BASE_URL` | Any OpenAI-compatible endpoint (`https://api.openai.com/v1`, the AminiLLM gateway, a local proxy). |
| `CANON_LLM_API_KEY` | Bearer credential for that endpoint. |
| `CANON_LLM_MODEL` | Text model identifier, passed through verbatim. |
| `CANON_LLM_VISION_MODEL` | Multimodal model identifier for image description. |
| `CANON_LLM_TIMEOUT_S`, `CANON_LLM_MAX_RETRIES` | Failure budget. |

Rules that follow from this:

- **Model identifiers are opaque strings.** No allow-list, no enum, no branching
  on model name. A new model is a config change, never a deploy.
- **No provider SDK outside the adapter.** The domain and use cases know
  `LLMPort` / `VisionPort`; they never learn which vendor answered.
- **Concept art is unreleased IP.** Pointing `CANON_LLM_BASE_URL` at the on-prem
  gateway keeps it on the premises and makes the privacy question a deployment
  decision rather than a product one.
- **Every LLM feature degrades to absent.** Disabled, misconfigured, timing out
  or rate-limited SHALL all behave the same way: the feature is unavailable and
  everything else works. Nothing in the validation, compilation or lookup paths
  may depend on a model being reachable.

## Derived Metadata — proposals, never authored content

The system MAY generate descriptions, tags and **suggested aliases** from a
concept view or a preview mesh. That output is **derived**, and derived content
lives in the rebuildable index keyed by the blob's content hash — never in
`asset.yaml`, never in the compiled `art-spec.md`.

The bridge between derived and authored is a **human accepting it**. An accepted
alias is written into `asset.yaml` as ordinary human-authored content, attributed
to the person who accepted it. This is the same two-exit discipline as
annotations: a proposal either gets promoted by a person or stays out of the
canon.

Two failures this prevents:

1. **Context poisoning.** If generated prose were compiled into `art-spec.md`,
   agents would read machine paraphrase as art direction, and the briefing would
   drift with nobody having said anything.
2. **Diff churn.** Regenerating a description on every ingest would rewrite
   `asset.yaml`, ruin `git blame`, and make spec review worthless.

The highest-value use is **alias suggestion**, because it feeds the deterministic
search already chosen (aliases + FTS) while keeping results correct rather than
probabilistic. For meshes, prefer `MeshFacts` — those are facts, not guesses.

## Agent Access — identity, authorization, lens

An agent connecting over MCP does **not have a role**. It acts **as a person**,
with exactly that person's permissions, and can never do anything that person
could not. Three layers, and only the last is the agent's to choose:

| Layer | Question | Source |
|---|---|---|
| **Identity** | Who is this? | The credential the process was launched with. **Never a tool parameter.** |
| **Authorization** | What may it do? | The owning actor's roles, decided in the domain. |
| **Lens** | What shape of information does it want? | A free parameter on read tools, carrying **no** authority. |

- **A lens is presentation, not permission.** An agent can send any string it
  likes, so a lens SHALL NOT widen access. Available lenses — `design`, `art`,
  `modeling`, `code` — shape which fields a read returns, so a Blender agent
  needing four constraints does not receive the whole spec.
- **One parameterized surface, not one tool set per discipline.** Four tool sets
  drift the way four validators drift.
- **The agent is an instrument, not an author.** Writes are attributed to the
  person *and* the agent — "rafa, via blender-agent" — so history stays
  followable and the human stays accountable.
- **Promotion is never agent-callable**, not even for an art director's agent.
  Promotion writes durable constraints; an agent raising a budget so its own
  output passes is how trust dies in week two.

## Deployment — Coolify

CyberCanon deploys to the Cyberdyne Coolify instance at
`https://coolify.cyberdynecorp.ai`, alongside its siblings (CyberdyneAuth,
CyberdyneRAG, the DAO backend), following the same
`<service>.backend.coolify.cyberdynecorp.ai` host convention.

**What deploys, and what deliberately does not:**

| Component | Deployed | Notes |
|---|---|---|
| `services/cybercanon/api` (FastAPI) | yes | HTTP surface for the web app |
| `apps/cybercanon/web` (SvelteKit) | yes | Static or node adapter |
| PostgreSQL | yes | The **rebuildable index**, not a source of truth |
| MinIO | yes | Blob mirror: views, exports, preview GLBs |
| `services/cybercanon/cli` (`canon`) | **no** | Runs on the artist's and programmer's machines |
| `services/cybercanon/mcp` (FastMCP) | **no** | **stdio, local-first by design.** Deploying it would mean an open port, CORS and a network threat model — all of which local-first exists to avoid. |

**Consequences that bind the design:**

- **Configuration is environment variables, with no file fallback.** Coolify
  supplies configuration as environment; twelve-factor is the native shape here,
  not an aspiration. No secret is ever committed, and no configuration is baked
  into an image.
- **The project's identifier is configuration, and it is the address.**
  `CANON_PROJECT` names the project a deployment serves, and that one string is
  the address in `/{version}/projects/{project}/…`, the subject the entitlement
  decision is taken over, the key the index rows are written under and the
  directory the working copy lives in. It is deliberately not derived from the
  repository URL or read out of the working copy's `.canon/project.yaml`: those
  two disagree in the ordinary case (`ronin` and `Ronin`), and an entitlement
  that changed when somebody edited a file in the repository would be an address
  that stopped working after a commit.
- **The API and the web application are different origins**, so the API names
  the origins a browser may read it from (`CANON_WEB_ORIGINS`), per environment
  and never as a wildcard. Without it the application shows an unavailable state
  against a service whose readiness is green — an outage with nothing in the
  logs.
- **Images are built once and promoted.** Nothing environment-specific at build
  time, so the same image runs in every environment.
- **Every deployed service exposes a health endpoint** that reports ready without
  requiring a model, an identity service or a sibling backend to be reachable —
  otherwise one dependency's outage cascades into a failed deploy.
- **Database migrations run as a release step**, and the index schema is
  droppable-and-rebuildable by definition, which makes a failed migration
  recoverable by rebuilding rather than by restoring a backup.
- **Persistent volumes** are required for PostgreSQL and MinIO. Losing either is
  recoverable — the index rebuilds from the repository, and blobs re-mirror from
  it — but the recovery must be a documented, tested operation, not a hope.
- **`CANON_LLM_BASE_URL` points at the on-prem gateway from inside Coolify's
  network**, which keeps unreleased concept art on the premises and makes the
  privacy question a deployment setting rather than a product argument.

**Resolved — how the hosted API reaches the git repository.** Git is the source of
truth, and the hosted API must read specification files that live in a game
repository. The decision, taken 2026-09-17:

- **Reads:** a **persistent working copy per project** on a volume, refreshed by a
  scheduled fetch and by webhook. Reads are served from the git object database at
  a pinned revision, so a fetch in progress never yields a torn read.
- **Writes:** a **direct commit to a configured branch** — not a pull request —
  authored as the acting person through the `.canon/actors.yaml` mapping. A person
  with no mapped git identity is refused, with a message naming the missing entry.
- **Rejected:** reading through a git host's API, which removes the volume but adds
  rate limits, per-read latency, a hard dependency on the host being up, and a
  second `SpecStore` implementation that would behave differently from the local
  one — reintroducing the "passed on my machine, failed on the site" class of bug.
- **Cost accepted:** disk per project, a staleness window that must be visible in
  the UI, and per-file conflict handling on concurrent edits.

Owned by `add-web-backend` (`hosted-repository`); operational recovery when a
working copy is lost or diverges is owned by `add-coolify-deployment`.

**Implemented and drilled, M2.** The working copy, the index and the blob mirror
are all rebuilt from the remote by a drill that destroys all three and compares
every answer before and after — see [`docs/recovery.md`](../docs/recovery.md).
The one state that does not survive is a person's notification dismissals, which
`add-web-backend`'s D9 declares as the single deliberate exception rather than
discovering later.

## Testing — three layers, and the specs are the source

The spec deltas hold **657 GIVEN/WHEN/THEN scenarios**. They are not documentation:
they are the BDD suite, generated into Gherkin and executed.

| Layer | Tool | Covers |
|---|---|---|
| **Unit** | `pytest` | domain and application — pure, no I/O. The validator suite runs over hand-built `MeshFacts` with zero files on disk. |
| **Port conformance** | `pytest` | one parametrised suite per port, run against the in-memory fake **and** every real adapter, so a fake that lies fails the build. |
| **BDD** | `pytest-bdd` | the spec scenarios. `.feature` files are **generated** from `openspec/changes/*/specs/*/spec.md` and committed; CI regenerates and fails on any difference. |
| **E2E** | `playwright` | the web application across a viewport matrix including tablet width, plus subprocess runs of `canon`. |

**Nobody hand-writes a `.feature`.** A hand-edited feature is a fork of the spec, and
the generator overwrites it.

**Two gates, failing in opposite directions:**

1. A requirement with no scenario that executes → **fail**. Catches a requirement
   nobody verified.
2. A generated scenario with no step definition → **fail**, naming the spec file and
   line. Catches a spec that moved ahead of the code.

One gate alone is satisfiable by cheating: coverage-only lets someone write a
scenario that asserts nothing; step-completeness alone lets a requirement carry no
scenario. Together they pin the spec and the code to each other — which is the same
trick the validator plays on assets, applied to ourselves.

**Accept the consequence:** adding a requirement to a spec **breaks the build until
someone implements its step**. That is the feature, and it will be irritating in
exactly the moment it is working. The only escape is one explicitly-marked pending
list, reviewed like any other exception — never a silent skip.

`just check` runs unit + BDD + conformance + both gates. E2E is `just test-e2e`,
gated behind a compose stack, so `check` stays fast enough to run constantly.
Coverage thresholds apply to the **domain package only** — elsewhere a number just
produces tests written to move the number.

## Gate Decisions (G1, G2, G4)

> **Status: working assumption, recorded 2026-09-19.** These were derived from
> decisions already binding above, not chosen freely. They govern `add-web-backend`
> and everything after it. Override them before M2 starts; after that they are
> expensive.

### G1 — Server-side validation and the preview pipeline

A **worker in the API deployment** runs the existing `validate_export` use case
when the working copy fetches a changed export. The preview is emitted by that
same run and mirrored to blob storage keyed by the export's content hash.

- **Same use case as the CLI and MCP.** No third implementation — that rule does
  not bend for a worker.
- **Not in the request path.** Mesh loading is unbounded work; an HTTP handler that
  waits on it is a timeout with extra steps.
- **Large exports:** an adopting repository is expected to track `exports/` with Git
  LFS, and the working copy uses a partial clone fetching LFS objects on demand.
  Rejected: keeping full history of multi-GB binaries on the volume.
- **Rejected:** artists uploading previews by hand — it puts a mechanical step back
  on the person the validator exists to protect.

### G2 — Where a validation outcome durably lives

A validation outcome is **repository content**, written as a file beside the asset
and committed by the worker.

This is forced, not chosen: `hosted-repository` requires that no write reach only
the index, `asset-spec` requires that dropping the index loses nothing, and
`asset-lookup` requires `where_is` to report which export was validated and when.
An index row satisfies none of those.

- **Evidence this is real:** M1 shipped code that *reads* an asset's validated
  export and date; nothing in the product *writes* them. That half of `where_is`
  is currently always empty.
- **Attribution:** the reporting actor, or automation when there is no person.
- **Cost accepted:** a commit per validation run. Mitigated by committing only when
  the verdict or the export hash changes, so a repeated run of an unchanged export
  writes nothing.

### G4 — Role vocabulary and the operation matrix

The role set is already implemented in the domain (M1):
`ART_DIRECTOR | ARTIST | DESIGNER | ENGINEER`.

| Operation | Who |
|---|---|
| Read a project | any entitled actor, including the local unauthenticated one |
| Search, lookup, compile, validate | same as read — never role-gated |
| Create an annotation | any actor with project write access **and** a mapped git identity |
| Reply in a thread | same |
| Resolve an issue | its author, or `ART_DIRECTOR` |
| **Promote to a rule** | **`ART_DIRECTOR` only** — and never an automated caller, for any role |
| Accept a suggested alias | `ART_DIRECTOR`, or the owner of the relevant discipline |
| Transition an asset's status | the owner of the relevant discipline, or `ART_DIRECTOR` |
| Raise an asset request | any mapped actor with read access |
| Accept or decline a request | the assigned discipline owner, or `ART_DIRECTOR` |
| Author durable content as an agent | **nobody** — refused for every role |

Group→role mapping stays configuration in the CyberdyneAuth adapter; the matrix
above is domain policy and is decided in the core.

**"Any mapped actor with read access" is the stricter of two readings, and it is
deliberate.** `asset-requests` says *"Any actor permitted to read a project SHALL
be permitted to raise a request within it"*; `hosted-repository` refuses a write
by a person with no mapped git identity, naming the missing entry, and
`add-web-backend`'s D7 accepts the consequence in so many words — *"a person who
has never been mapped cannot even accept a request"*. Both cannot hold for an
unmapped reader. **Read access *and* a mapped identity** is what is implemented,
in the domain, for every mutating operation: a request is repository content, an
unattributable workflow record is the thing the two-identity rule exists to
prevent, and a refusal that names the missing mapping is fixed by one line in a
file. The two specification deltas disagree on this point and one of them is
wrong; the code does not split the difference.

### G3 — Asset creation, spec editing, and the status lifecycle

> **Working assumption, recorded 2026-09-22**, derived from decisions already
> binding rather than chosen freely. Needed by S16. Override before M3 starts.

**Creation.** An asset comes into existence in exactly three ways, all writing the
same minimal identity-only specification through the same use case: `canon new
<id>` on the command line, a concept upload that names an asset which does not yet
exist, and an explicit creation on the web surface. Creation is a commit like any
other write — attributed, reviewable, refused for a person with no mapped git
identity.

**Spec editing.** The web surface edits *declared fields*, not YAML text. The
round-trip writer already preserves comments and key order, so an edit produces a
reviewable diff. Free-form YAML editing is deliberately not offered: the schema is
the contract, and a text box invites a file that parses and means nothing.

**Status transitions.** The lifecycle is ordered:
`concept → approved → modeling → validated → in-engine`.

| Move | Who | Rule |
|---|---|---|
| Forward one step | the relevant discipline owner, or `ART_DIRECTOR` | never skip a step; a skip is refused naming the step that was missed |
| Backward, any distance | the same | always allowed — an asset can always go back to modeling |
| Into `validated` | **nobody** | set only by the validation worker when an export passes, never by hand |
| Into `in-engine` | discipline owner or `ART_DIRECTOR` | requires the asset to be `validated` first |

`validated` being unreachable by hand is the point, and it follows from G2: the
status then *means* an export passed, rather than meaning someone clicked. It is
the same closed loop as sockets and clips, applied to the lifecycle.

## Visual language — neo-brutalism

> **Decision, recorded 2026-09-23.** This supersedes the earlier assumption that
> the web application would be built on `@cyberdynecorp/svelte-ui-core`.

CyberCanon's visual language is **neo-brutalism**: heavy borders, hard offset
shadows, flat saturated colour, no gradients, no soft radii. The tokens come
from the project's own design source and live in one place.

**Why this and not the Cyberdyne design system.** The shared system is
dark-first and cyberpunk, and the packages were never installed here — task 1.2
has been open since the shell was built, waiting on private-registry
credentials, which means the `D4` test that was meant to stop a local component
reimplementing a design-system primitive has been guarding nothing. Rather than
leave the specification asserting one thing while the repository does another,
the divergence is recorded as a decision.

**Consequences:**

- `add-web-app-shell` task 1.2 and design decision D4 are superseded by this
  section. The D4 test becomes a check that components consume the **project's
  own tokens** rather than hard-coding a colour, a font or a shadow.
- **Tokens live in exactly one file.** A component that writes a hex value, a
  font stack, a border width or a shadow offset inline is a bug, and the check
  is mechanical rather than a review habit.
- **Neo-brutalism is a style, not an excuse.** Every requirement the shell
  already carries still holds: the closed route-state set, a partial result
  never presented as complete, attribution visible on every screen, and an
  expiring session never destroying unsaved work. A restyle that loses a
  disclosure has broken the product, not improved it.
- **The contrast obligation is higher, not lower.** Flat saturated colour on
  flat saturated colour fails legibility easily, and this interface is read on
  an iPad in a studio. Every text-on-background pair meets WCAG AA.

## Planned Changes

| # | Change | Capabilities | Status |
|---|---|---|---|
| 0 | `add-test-strategy` | *(no spec deltas — tooling)* | specified |
| 1 | `add-asset-spec-and-validator` | asset-spec, asset-validation, asset-preview, spec-compilation, canon-cli | specified |
| 2 | `add-mcp-read-server` | mcp-server, asset-lookup, spec-lenses, agent-identity | specified |
| 3 | `add-derived-metadata` | llm-integration, derived-metadata, metadata-acceptance | specified |
| 4 | `add-web-backend` | http-api, auth-integration, hosted-repository, blob-storage, asset-requests | specified |
| 4b | `add-web-app-shell` | app-navigation, asset-browser, web-session | specified |
| 5 | `add-concept-ingestion` | concept-ingestion, view-versioning | specified |
| 6 | `add-model-sheet-2d` | annotation-authoring, annotation-triage, model-sheet-2d | specified |
| 7 | `add-viewer-3d` | viewer-3d, anchor-resolution, animation-playback | specified |
| 8 | `add-cyberarche-integration` | document-platform, semantic-search-delegation | specified |
| 9 | `add-mcp-writes` | mcp-write-surface | specified |
| 10 | `add-coolify-deployment` | deployment-operations | specified |

Milestones, the reasoning behind this order, the decisions that gate each one, and
the product boundary live in [`ROADMAP.md`](../ROADMAP.md).

**This table is the authority on ordering.** A proposal cites its number here; two
changes never share a position. Changes 4 and 5 are ordered as listed:
`add-concept-ingestion` depends on `hosted-repository`, so the backend precedes it.

Changes 1–3 are usable by programmers **without any artist changing a habit**.
That ordering is deliberate: it avoids the adoption cliff, and the artist-facing
interfaces arrive when spec files already exist and have proven their value.

## Identity Mapping — do not defer this

Because git is the source of truth, every person has **two identities**: the
CyberdyneAuth `sub` and the git commit author. Unlinked, the Rafa who annotated
in the web app and the `rafa@cyberdyne.com` who committed `asset.yaml` are two
different people in the history, and attribution — half the value of the tool —
breaks silently. Claims carry it when CyberdyneAuth can; otherwise
`.canon/actors.yaml` maps `sub` → git emails → discord → default role. Cheap now,
ruinous to reconstruct after six months of history.

## Deliberately Deferred

pgvector/multimodal RAG in CyberCanon (aliases + FTS + CyberArche RAG cover it;
reassess around ~5000 assets and log zero-result queries in the meantime); a
formal asset dependency graph (`links:` covers the real case); mass-variation
triage/voting; an AI auto-correction loop that rewrites meshes to satisfy the
linter; full paint-over with brushes and layers; a hosted multi-tenant MCP mode.

## Conventions

- Medium/large or auth/security/data-model changes go through OpenSpec.
- Every bug fix ships a regression test in the same change.
- RFC-2119 language in specs (SHALL/MUST/MAY). Every requirement has ≥1 scenario.
- Backend cognitive complexity target ≤15 per function; frontend 8–12.
- Never mention AI authorship in commit messages or PRs.
