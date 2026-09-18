# Proposal

## Why

The original complaint from developers was not "search is bad" — it was **"I don't
know where to get the concept or the 3D model."** That is a lookup problem, and
with `asset.yaml` files now in the repository it is answerable by a dictionary
read over files that already exist.

This is **roadmap position 3**, and it comes now for the same reason the validator
came first: it delivers value to programmers and to the agents they already run —
Claude Code, Cursor, the Blender agent — **without a single artist changing a
habit**. It is the last change in the sequence that requires no artist-facing UI,
and it is what makes the spec files earn their keep before anyone is asked to
maintain them.

It also closes the design→art→code loop in the direction that was still open: a
modeller's agent can now ask *what must this mesh satisfy* before modelling
begins, rather than discovering it when the validator rejects the export.

## What Changes

- **A local stdio MCP server** shipped in the same binary as `canon`, spawned as a
  child process by the agent that uses it. No open port, no CORS, no local network
  surface.
- **`where_is`** — the highest-value tool, implemented first: given an asset id,
  return the repo directory, authoring source file, latest validated export,
  engine content path, discussion link, and current status with its three owners.
- **A read surface**: `list_assets`, `get_asset_spec`, `get_constraints`,
  `get_open_annotations`, `diff_spec`, `validate_export`, `search_assets`.
- **Discipline lenses** — `design | art | modeling | code` — parameterising what
  `get_asset_spec` returns, so an agent needing four constraints is not handed the
  whole specification. **One parameterised surface, not four tool sets.**
- **A rebuildable local index** — a repo scan producing a lookup and full-text
  index over ids, names, aliases, tags and status. Deletable and reconstructible
  at any time; no server, no PostgreSQL in this change.
- **Search by alias**, scoped per project, ranked `exact id > name prefix > alias >
  tag > description substring`, with **zero-result queries logged** so the misses
  tell us which aliases to add.
- **Prose responses, not raw JSON** — results land in a context window, so
  `get_asset_spec` returns the markdown a human would read.
- **Identity rules for agent callers** — identity comes from the credential the
  process was launched with and is never a tool parameter; a lens carries no
  authority; writes would be attributed to the person *and* the agent.
- **The actor mapping** — `.canon/actors.yaml`, authored in the repository, binding
  a person's identity subject to their display name, their git author emails, an
  optional chat handle and a default role. Because git is the source of truth every
  person has **two identities**, and unlinked they become two people in the history;
  this change links them while the history is still short. Provider claims win where
  they carry the link, so the file is a fallback rather than a parallel identity
  store, and an unmapped git author resolves to an explicitly **unknown** actor that
  is reported as unmapped — never silently attributed to someone else, never dropped.
- **Attribution resolves through that mapping** — `where_is` and every listing that
  names an owner present the person, not a raw email or subject.
- **`validate_export` reuses the existing use case** — no second implementation of
  any rule.
- **Promotion is deliberately absent** from the tool surface, and this change
  specifies that absence as a requirement rather than leaving it an oversight.

## Capabilities

### New Capabilities

- `mcp-server`: the MCP transport and tool surface — stdio, one binary serving
  both the programmer's and the artist's machine, prose-shaped responses, error
  behaviour, and the read-only boundary.
- `asset-lookup`: answering *where is this asset* and *which assets exist* —
  `where_is` resolution, listing and filtering, alias-aware ranked search,
  zero-result logging, and the rebuildable index the answers come from.
- `spec-lenses`: the discipline lens that shapes which fields a specification read
  returns, and the rule that a lens narrows presentation without widening access.
- `agent-identity`: how a caller is identified, what it may do, how its actions
  are attributed, and what no agent may ever do regardless of who it acts as —
  including the actor mapping that binds an identity subject to the git author
  emails that person commits under, in both directions.

### Modified Capabilities

None. The new command-line entry points — launching the server and rebuilding the
index — are specified inside `mcp-server` and `asset-lookup` respectively, rather
than as a delta against `canon-cli`, which change 1 has not yet archived.

## Non-goals

Explicitly **not** in this change:

- **No MCP write tools.** `add_annotation` and `report_export` are roadmap
  position 6, after trust in the read surface is established. This change is
  read-only apart from index maintenance.
- **No promotion tool, ever.** Not deferred — prohibited, and specified as such.
- **No hosted or multi-tenant MCP mode.** Local stdio only; a network transport is
  a separate change with its own threat model.
- **No PostgreSQL and no MinIO.** The index is local and rebuildable. The server
  index arrives with the first server surface.
- **No semantic search, no embeddings, no pgvector.** Aliases plus full text,
  with misses logged to tell us later whether embeddings are warranted.
- **No LLM calls.** This change reads files; `add-derived-metadata` owns anything
  that talks to a model.
- **No CyberdyneAuth network integration.** Identity resolution is specified so
  the rules exist, but an unconfigured identity degrades to a local actor rather
  than requiring a running auth service — reads must work offline.
- **No writing the actor mapping.** The file is authored by a person and reviewed
  in a pull request like any other specification content; nothing here creates,
  edits or infers an entry, and no unmapped author is auto-bound to a similar name.
- **No committing on a person's behalf.** Resolving an actor to the git identity
  used for such a commit is specified here because attribution needs it; the
  surface that actually commits is not part of this read-only change.
- **No web UI.**

## Impact

- **New code** — `libs/cybercanon/application/ports/search_index.py`, use cases
  `where_is`, `list_assets`, `search_assets`, `get_open_annotations`, `diff_spec`,
  `compile_spec_for_lens`, `rebuild_index`;
  `libs/cybercanon/adapters/inbound/mcp/`;
  `libs/cybercanon/adapters/outbound/sqlite_search.py`;
  `services/cybercanon/mcp/`.
- **New dependency** — `fastmcp`. SQLite comes from the standard library.
- **Extended** — `SpecStore` gains history access (`diff_spec` needs the previous
  revision of a spec file from version control) and a project-scoped read for the
  actor mapping; `Actor`, `Role`, `GitAuthor`, `ActorBinding` and `ActorMapping`
  enter the domain, with resolution and the mapping's structural rules as pure
  functions; `IdentityProvider` may optionally supply a person's git author emails,
  which take precedence over the file; the composition root gains a second inbound
  adapter, which is the first real test of the one-core claim.
- **Consumer-side impact** — an agent configuration entry pointing at the `canon`
  binary; a `CLAUDE.md` line telling repo-reading agents that specifications exist
  and where. A game repo gains a git-ignored local index file, and an optional
  committed `.canon/actors.yaml` whose entries are reviewed like any authored
  content. A repository without that file stays fully readable, with every git
  author reported as unmapped and listed for completion.
