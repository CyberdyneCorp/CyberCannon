# Design

## Context

Change 1 established the domain, the ports and one inbound adapter. This change
adds the **second** inbound adapter, which is the first real test of the "one
core, three surfaces" claim in `openspec/project.md`. If the MCP server ends up
with logic the CLI does not have, the claim was false and the product acquires
the bug it exists to prevent.

See `proposal.md — Why` for motivation. Two constraints from `project.md` govern
everything below: **agents read constraints, agents never write constraints**, and
the git working copy is the source of truth.

## Goals / Non-Goals

**Goals:**

- Prove the one-core claim structurally, not by discipline.
- Make `where_is` answerable in a single, obvious call — it is the tool that
  answers the original complaint.
- Keep every read working with no credential, no network and no services.
- Make the identity rules testable without an identity provider existing yet.

**Non-Goals (design level):**

- No caching strategy beyond index freshness. A repository at this scale scans in
  well under a second.
- No streaming or pagination protocol. Listings are compact tables; a project with
  enough assets to need pagination is a signal to revisit search, not to add
  paging.
- No concurrency. One agent, one process, one request at a time.

## Decisions

### D1 — The MCP adapter is a formatter, and that is enforced

The adapter's only jobs are: map tool arguments to a use case call, and render the
result as prose. A structural test asserts that `adapters/inbound/mcp/` contains no
conditional on specification content and imports nothing from `adapters/outbound/`.

*Why:* this is the change where drift starts, because prose rendering feels like a
good place to "just add" a fallback. `import-linter` catches the import; the
structural test catches the logic. **Alternative rejected:** trusting review — the
CLI and MCP renderers will be written weeks apart by different people.

### D2 — Rendering lives in the application layer, keyed by lens; the adapter picks a key

`compile_spec_for_lens(asset, lens) -> str` is a use case. Both the CLI's
`canon compile` and the MCP `get_asset_spec` call it. The lens selects a **field
projection** applied to the already-compiled specification, never a second
compiler (`spec-lenses` requires exactly this: one compilation, four projections).

*Why:* if each lens rendered independently, the `design` and `modeling` lenses
would eventually disagree about what the sockets are — and sockets are the closed
loop's payload. **Alternative rejected:** four templates, which reads more clearly
per lens and guarantees divergence.

### D3 — Lens is presentation; authorization is evaluated before the lens applies

Order is fixed: resolve actor → authorize the read → compile → project the lens.
The lens parameter never reaches the authorization decision.

*Why:* the spec requires that a lens cannot widen access. Making it an ordering
property rather than a check means there is no code path where a lens could be
consulted for permission. A caller may request any lens precisely because the
lens carries no authority — which is only safe if authorization already happened.

### D4 — `Actor` resolution is a chain of providers ending in a local actor

`IdentityProvider` resolves a credential to an `Actor`. The composition root wires
a chain: configured credential → cached actor (TTL) → **local unauthenticated
actor** with read-only entitlement to the project on this machine.

*Why:* `agent-identity` requires reads to work with no identity and to survive an
identity outage, while still refusing role-requiring actions. A chain makes the
degradation explicit and testable rather than a scatter of `if provider is None`.
The CyberdyneAuth adapter slots in as the first link in a later change without
touching the others.

*Consequence:* "may this actor read this project" is a real domain policy from day
one, even though the only actor today is local. That policy is where the
CyberdyneAuth group → project mapping lands later.

### D5 — Attribution is a value object with two slots, required at construction

`Attribution(actor: ActorId, via: AgentId | None)`. Any recorded action takes one,
and there is no constructor that omits the actor.

*Why:* `agent-identity` requires that an unattributable action be refused rather
than recorded anonymously. Making the actor non-optional in the type means the
refusal is a compile-shaped guarantee rather than a validation someone forgets.
Nothing in this change records actions — the writes change does — but the type
must exist now, because retrofitting attribution after history accumulates is the
identity-mapping mistake `project.md` warns about, in miniature.

### D6 — The prohibition on promotion is a test, not an absence

A test enumerates the advertised tool names and asserts the set matches an
expected list exactly, failing when anything is added. A second test asserts no
advertised tool mutates repository content, by running every tool against a clean
working tree and checking it is still clean.

*Why:* `mcp-server` specifies that promotion is prohibited in this *and any future
version*. An absence cannot be enforced by absence; someone adds a tool in six
months and nothing objects. An exact-match test turns "we decided not to" into "you
must edit this list and explain yourself."

### D7 — SQLite FTS5 for the index, in a git-ignored file under `.canon/`

Standard library, single file, no server, deleteable. The index stores ids, names,
aliases, tags, status, owners, link targets and a content hash plus mtime per spec
file.

*Why:* local-first, and the index must be disposable by specification. **Alternative
rejected:** an in-memory scan per invocation — simpler, but the MCP server is a
long-lived process and a full rescan per call is wasteful once a project has a few
hundred assets. **Deferred:** PostgreSQL, which arrives with the first server
surface and replaces this behind the same `SearchIndex` port.

### D8 — Staleness is detected per file by hash, and the read path self-heals

Every lookup compares the indexed file's mtime and size before trusting it; on a
mismatch it re-reads that one file and updates its row. A full rebuild is a command,
not something a read triggers.

*Why:* `asset-lookup` forbids serving a stale answer as current. Per-file checking
makes the common case — one file edited — cost one stat call, while keeping the
guarantee. **Alternative rejected:** a file watcher, which adds a dependency and a
failure mode for a problem a stat call solves.

### D9 — Ranking is a fixed ordered cascade, not a score

Five passes in order — exact id, name prefix, alias exact, tag exact, description
substring — concatenated with duplicates removed, each pass internally sorted by
identifier for determinism.

*Why:* the spec defines the order, and a cascade makes it inspectable and stable.
A relevance score would need tuning, and its results would change under us for
reasons nobody could explain. **Alternative rejected:** FTS5's BM25 ranking, kept
available for the description pass only.

### D10 — `diff_spec` compares parsed specifications, not file text

`SpecStore` gains history access; the previous revision is parsed into the same
domain objects and compared field by field, producing semantic statements
("triangle budget 12000 → 9000").

*Why:* a raw file difference is unreadable in a context window and reports
reformatting as change. The domain already has the objects. **Cost accepted:** the
`SpecStore` port grows a history capability, which `GitSpecStore` implements by
reading an earlier revision of the file — the one place this change genuinely needs
version control rather than just a file system.

### D11 — Zero-result queries are logged locally and never leave the machine

Appended to a local file under `.canon/`, retrievable by a command. No upload.

*Why:* the value is deciding which aliases to add; that decision is made by someone
reading the list. Shipping queries anywhere invites a privacy conversation for no
benefit at this stage.

### D12 — The actor mapping is domain data read through `SpecStore`, and resolution is a pure function

The domain gains `GitAuthor(email)`, `ActorBinding(subject, display_name, emails,
chat_handle, default_role)` and an `ActorMapping` value object holding the
bindings. Resolution in both directions — email → `Actor`, `Actor` → `GitAuthor` —
is a pure function over `ActorMapping`, alongside the structural rules (duplicate
subject, duplicate email, unknown role, no email) which return ordinary
`Violation` values. Reading `.canon/actors.yaml` is an adapter concern: it is a
repository file like `asset.yaml`, so it is fetched through `SpecStore`, at the
same revision as the specs it explains. Translating provider claims into
`ActorBinding` is the `IdentityProvider` adapter's job; no claim name, group name
or token field is visible to the resolution function.

*Why:* deciding who a person is belongs to the same class of decision as deciding
whether a mesh passes, and must be testable with hand-built mappings, no files and
no auth service — the same boundary that makes the validator suite run on
`MeshFacts`. **Alternative rejected:** a dedicated `ActorDirectory` port, which
would make identity a second I/O path and invite an implementation that reads the
index — the exact shape `project.md` forbids, since the mapping would stop being
reviewable in git. **Cost accepted:** `SpecStore` now carries a file that is not
an asset specification, so the port grows a project-scoped read beside its
asset-scoped one.

### D13 — Claims first, the file second, and the disagreement is reported

Resolution order is fixed: provider claims → mapping file → unknown actor. The
file is not consulted for a person the provider fully describes, and where both
describe the same subject differently the provider wins and the difference is
emitted as a violation rather than merged.

*Why:* the file exists because CyberdyneAuth may not carry git emails today, not
because the repository should own identity. With claims first, the day the
provider grows that claim the file quietly stops mattering — no migration, and no
ambiguity about which one is true. **Alternative rejected:** file-first, which is
more deterministic, works offline and is reviewable, but makes every project carry
a parallel identity store forever and guarantees drift from the provider.
**Cost accepted:** two sources of the same fact during the transition, and a
disagreement nobody may notice; mitigated by shaping the disagreement as a
validation violation that the existing lint path already surfaces.

### D14 — An unmapped author is a value, not a null

Resolution always returns an `Actor`. An unmatched email yields one marked
unmapped, carrying the raw email and holding no roles. There is no signature in
the chain that returns `None`.

*Why:* the spec requires that authorship is never dropped and never guessed. An
optional return puts that requirement at every call site, and one forgiving `or
current_actor` silently misattributes history — precisely the failure the mapping
exists to prevent. **Alternative rejected:** raising on an unmapped author, which
turns an incomplete mapping into a broken read of any repository whose history
predates CyberCanon, and there is always such history. **Cost accepted:** every
renderer must handle the unmapped marker, enforced by tests that render an
unmapped owner through `where_is` and through each listing.


## Risks / Trade-offs

- **The MCP adapter grows logic anyway** → D1's structural test plus D6's tool-set
  test. Both fail loudly in CI rather than being noticed at review time.
- **Prose responses are untestable in the usual way** → Assert on content
  (does the `modeling` lens response contain the required socket and not the
  palette), never on exact wording, so rendering can be improved without
  rewriting tests.
- **An agent treats a lensed read as the whole truth** and models against a subset
  → Every lensed response states which lens produced it and that a full
  specification exists. Cheap, and it prevents the worst misreading.
- **`diff_spec` against a shallow clone or a repository without history** → Report
  that history is unavailable for the requested range rather than failing the tool;
  a degraded answer beats a broken session.
- **Identity rules are specified before an identity provider exists**, risking a
  design that does not fit CyberdyneAuth → Mitigated by keeping the domain to
  `Actor` + `Role` and putting every claim, group and token concern behind the
  provider, exactly as CyberArche's integration does. The open questions in
  `project.md` about CyberdyneAuth's group model change the adapter, not this
  change's specs.
- **Cost accepted:** an index that must be kept honest, for read latency that a
  full rescan would also have delivered at today's scale. The bet is on asset count
  growing, and on the same `SearchIndex` port later serving the web app.
- **A stale actor mapping mis-binds a reused email address** — a contractor's
  address reassigned to someone else → Matching is exact and never fuzzy, the file
  is reviewed in a pull request like any authored content, and a person changing
  address adds an email rather than replacing one, so old commits keep resolving.
- **Nobody ever writes the mapping** and every author stays unmapped → The
  unmapped-author list is retrievable and mapping validation runs in the same lint
  path as the specification files, so an empty mapping is a visible defect rather
  than an invisible one.
- **Cost accepted:** identity mapping is specified in a change that never commits
  anything, so the actor → git author direction has no caller until a write-back
  surface exists. Paying now is deliberate: `project.md` calls reconstructing
  attribution after six months of history ruinous, and the read surface already
  names owners today.

## Migration Plan

Additive. A repository without an index builds one on first use; a repository that
never launches the server is unaffected. `.canon/index.sqlite` and the query log
are git-ignored. Rollback is removing the agent client's configuration entry —
nothing in the repository changes.

`.canon/actors.yaml` is optional and additive in the same way: a repository
without it stays fully readable and reports every git author as unmapped.
Adopting it is adding the file; back-filling it is reading the unmapped-author
list and adding an entry per person; correcting it is an ordinary commit that
takes effect on the next read. Rollback is deleting the file, which returns every
author to unmapped and breaks nothing.

## Open Questions

- **Whether `where_is` should report the engine path's existence on disk**, which
  requires knowing where the engine project is checked out. Answerable from the
  project configuration later; it adds a field to a response and changes no
  specification.
- **The cached-actor time-to-live.** A configuration value; the degradation
  behaviour it governs is already specified.
- **Whether CyberdyneAuth will carry git author emails as a claim.** Unanswerable
  from here, and it does not need answering: D13 makes it a configuration outcome —
  if the claim appears the file stops being consulted, and if it never appears the
  file remains the answer. Neither case changes a requirement.
