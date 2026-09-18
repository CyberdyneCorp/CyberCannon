# Design

## Context

Changes 1–3 deploy nothing. Every surface built so far runs on a machine that
already has the repository, so "where does the specification come from" was never a
question: it was a path argument. This change is the first one that has to answer
it from a container, for several people at once, and `project.md` records that
question as an explicit open tension that must be settled before the web surface is
specified.

It is settled here — **a persistent working copy per project, direct-commit
write-back** — and the rest of this document is mostly the consequences of that
sentence plus the consequences of one older sentence: *the CLI validator, the MCP
`validate_export` and the web Validate button are the same use case.* This is the
third inbound adapter. If it grows logic, the product acquires the exact bug it
was built to prevent, and this time the disagreement is visible to artists.

Ports touched: `SpecStore` (gains revision-pinned reads and a write-back
operation), `BlobStore` (gains content-addressed keys and link issuance),
`SearchIndex` (gains a PostgreSQL implementation), `IdentityProvider` (gains its
first real adapter), and two new ports — `RepositoryHost` (fetch, commit, push,
clone, recover) and `Notifier`. Domain objects touched or introduced: `Actor`,
`Role`, `Attribution`, `Tenant`, `Revision`, `ContentHash`, `AssetRequest`,
`RequestState`, `Discipline`, and the policy functions that decide who may do what.

## Goals / Non-Goals

**Goals:**

- Answer the git-access question with something that has a stated failure mode for
  every way it can break, rather than something that works on the happy path.
- Make "the database is not the source of truth" a property that is *tested*
  (drop it, rebuild, every answer identical) instead of a slogan.
- Keep authorization decisions in the domain, so they can be exercised with no
  identity service and no HTTP.
- Make attribution work end to end — a person edits in a browser and `git blame`
  names that person — because retrofitting it is the mistake `project.md` warns
  about.

**Non-Goals (design level):**

- No horizontal scaling of the API beyond one writer per project. A studio-sized
  workload does not need it, and a second writer per project would turn D5's
  precondition into a distributed lock problem.
- No caching layer in front of the index. The index *is* the cache.
- No real-time transport. Notification is polled; a request assigned to someone is
  not an event worth a socket.
- No offline-capable web client. The CLI is the offline surface, by design.

## Decisions

### D1 — A persistent working copy per project, not the git host's API

Each configured project gets a long-lived clone on a persistent volume. All reads
and writes go through it.

*Why:* the hosted surface must do exactly what the CLI does — walk upward for the
governing spec, read a project config, read several files as one consistent set —
and a contents API answers file-at-a-time, per host, under a rate limit, with a
different shape for GitHub, GitLab and a bare SSH remote. A clone makes
`GitSpecStore` the same adapter on a laptop and in a container.

**Alternative rejected:** read-through the git host's REST API. It removes the
persistent volume and the recovery procedure, and it was tempting for exactly that
reason — but it makes every project's availability depend on a third party's rate
limit, forbids a consistent multi-file read, and binds us to one host's API shape
in the adapter that is supposed to be host-agnostic.

**Cost accepted:** the API service becomes stateful. It needs a volume, a
provisioning state, a staleness story and a documented recovery — all of which are
specified rather than hoped for, and none of which threaten data, because the
working copy holds nothing the remote does not.

### D2 — Write-back is a direct commit to a configured branch

An accepted edit is committed and pushed to the branch named in project
configuration.

*Why:* the edits this surface makes — an accepted alias, a promoted rule, a request
transition — have already been reviewed by the person making them, in a tool
designed to make that review possible. A pull request would ask a second human to
approve a decision the first human was authorised to make, and the queue of
unmerged spec PRs would become the thing people route around.

**Alternative rejected:** a pull request per edit, or a long-lived `canon/` branch
merged periodically. Both give pre-merge review and a rollback point; both make the
tool's edits invisible until someone merges them, which breaks the promise that the
repository is the source of truth *now*.

**Cost accepted:** the configured branch must permit pushes from the service's
credential, so a studio that protects its default branch must configure a different
one. History gains many small commits. There is no pre-merge review of an edit made
through the tool — the tool's own authorization is the control, which is why D13
enumerates human-only actions rather than trusting the UI.

### D3 — Reads are served from the git object database at a pinned revision, never from the checked-out tree

`SpecStore` reads take a `Revision` and resolve content through git's object store
for that revision. The checked-out tree exists for writing.

*Why:* it makes `hosted-repository`'s read-isolation requirement structural rather
than a lock. A fetch updates a ref; a read holds a revision it already resolved, so
there is no window in which a reader observes a half-updated tree, and a compiled
briefing assembled from six files is assembled from one revision by construction.

**Alternative rejected:** reading the working tree under a reader-writer lock.
Simpler to write, and it serialises every read behind every fetch — the failure
mode being that a slow fetch on a large repository stalls the whole surface.

**Cost accepted:** `GitSpecStore` grows a second read path, and the local CLI's
"just read the file" path and the server's "read this revision" path must be
covered by the same port-conformance suite or they will drift.

### D4 — The scheduler is the guarantee; the webhook is an optimisation

A per-project timer fetches on an interval. A webhook, once its origin is
authenticated, triggers the same fetch immediately.

*Why:* webhooks are lost, misconfigured, and silently disabled by repository
administrators. Treating one as the only refresh path produces a project that is
quietly hours stale with nothing reporting it. Treating it as a hint means a
misconfigured webhook costs latency, not correctness.

**Alternative rejected:** webhook-only refresh, which is what "real-time" arguments
lead to. **Cost accepted:** a constant background fetch load proportional to the
number of projects, and a staleness window that is never zero — which is why it is
reported on every read rather than concealed.

### D5 — Conflict detection is per file, by the content hash the edit was based on

An edit carries the `ContentHash` of the file it was composed against. Write-back
re-reads that file at the current revision and refuses if the hash differs.

*Why:* the natural precondition is the branch tip, and it is wrong: any unrelated
commit anywhere in the repository would then conflict with every in-flight edit,
and a project with a busy branch would be unwritable. Per-file hashing conflicts
exactly when two people touched the same specification.

**Alternative rejected:** whole-repository revision preconditions (correct, useless
in practice) and three-way merging of YAML (no — a merged specification nobody
authored is worse than a refusal).

**Cost accepted:** two people editing *different fields of the same file* conflict,
and one of them retypes. That is the right trade at this granularity: an
`asset.yaml` is small, and a field-level merge would need semantic merge rules that
would themselves become a second source of truth about the schema.

### D6 — A rejected push is retried by re-checking the precondition, never by forcing

On rejection: fetch, re-evaluate D5's per-file hash, re-commit on the new tip, push
again, bounded to a small number of attempts, then report a conflict. No
force-push, no merge commit, no rebase of unrelated work.

*Why:* the rejection means somebody else pushed. If their commit did not touch this
file the edit is still valid and the retry succeeds invisibly; if it did, the edit
was based on content that no longer exists and must be refused. Both outcomes are
already the specified behaviour, so the retry is just the mechanism.

**Cost accepted:** a pathologically busy branch can exhaust the attempts and report
a conflict for an edit that would have applied. Reporting a false conflict is safe;
forcing is not.

### D7 — Asset requests are repository content, committed through the same write-back path

One file per request, under the project's `.canon/` directory, with its state
history in the file. Every transition is a commit.

*Why:* `hosted-repository` requires that dropping the index loses no answer, and a
request is an answer — it has an owner, a state and an attribution people rely on.
A PostgreSQL table would be faster, obvious, and would make the database
authoritative for a class of content, which is precisely the decision `project.md`
forbids. Keeping requests in the repository also means they are readable by the CLI
and by an agent reading the repo, with no new access path.

**Alternative rejected:** a requests table in the index, with "we'll export it if we
ever need to". That export never gets written.

**Cost accepted:** a commit per state transition, and git history that mixes
workflow churn with specification changes. Mitigated by one file per request — the
churn is confined to files nobody diffs for design intent. A second, sharper cost:
because every write needs an actors-mapping entry (D8), a person who has never been
mapped cannot even accept a request. That is deliberate; an unattributable workflow
record is the thing we are trying not to accumulate.

### D8 — Attribution resolves through `.canon/actors.yaml`, and an unmapped person is refused

The commit author is the git identity mapped from the verified subject. No mapping,
no write.

*Why:* `project.md` calls the two-identity problem "cheap now, ruinous to
reconstruct after six months of history". Committing as a shared bot identity with
the person's name in the message is the tempting fallback, and it is exactly how
`git blame` stops answering the question the tool exists to answer.

**Alternative rejected:** a service identity as author with the person in
`Co-authored-by` or the message body. Never blocks anyone; makes authorship
unqueryable by every tool that reads authorship.

**Cost accepted:** onboarding a person is a two-step operation — they can read
immediately, and cannot write until someone adds them to a file in the repository.
The refusal names the missing mapping, so the fix is obvious.

### D9 — Notifications are a derived view plus a per-person dismissal flag

There is no notification entity. "Unread items" is a query over requests where the
person is assignee or author, minus dismissals. Dismissal flags live in the index
only.

*Why:* it keeps `asset-requests`' durability requirement honest without committing a
read-receipt to git on every glance. The state that must survive an index rebuild —
the request, its assignee, its state, its attribution — is repository content; the
state that may be lost is whether someone has already looked at it.

**This is the one deliberate exception** to "the index holds nothing durable", and
it is stated here rather than discovered later: after an index rebuild, previously
dismissed notifications reappear as unread. The cost is one person clicking
dismiss again; the alternative is a commit per dismissal.

### D10 — Domain operations return typed outcomes; one function maps them to status codes

Use cases return a result union (`Ok`, `NotFound`, `Forbidden`, `Unauthenticated`,
`Invalid`, `Conflict`, `Unavailable`) carrying a stable error identifier and a
subject. One mapping function translates it. Routers do not catch exceptions and do
not construct status codes.

*Why:* `http-api` requires that a domain refusal never surfaces as an internal
error, and requires the same outcome to map identically on every endpoint. A
per-router `try/except` satisfies that on the day it is written and stops doing so
at the fourth endpoint. A single mapping is exhaustively testable — one test
asserts every member of the union has a mapping.

**Alternative rejected:** framework exception handlers per domain exception type,
which is idiomatic FastAPI and scatters the mapping across module import order.

**Cost accepted:** use cases stop raising and start returning, which is more verbose
at every call site, and the CLI and MCP adapters must be updated to the same shape.
That update is the point: three adapters translating one outcome vocabulary.

### D11 — Idempotency keys are stored in the index with a bounded lifetime, and D5 is the backstop

A key stores the request digest and the original outcome for a bounded period; a
replay within that period returns the stored outcome, and a replay with a different
body is refused.

*Why:* the surface must be safe to retry, and a lost response on a write that
already committed is the common case — a mobile network, a proxy timeout.

**Cost accepted:** the record lives in the index, so an index rebuild forgets it and
a very late retry could apply twice. It cannot, in practice, because D5's per-file
precondition refuses the second apply: the content the retry was based on is no
longer current. The two mechanisms interlock deliberately — idempotency makes the
retry *quiet*, the content hash makes it *safe*.

### D12 — Claims are translated by the adapter into `Actor`; the domain never sees a token

The auth adapter verifies the signature against a cached key set, checks issuer,
audience and validity, then maps configured groups to `Role`s and the subject to an
`ActorId`, producing an `Actor` with a `Tenant`. Authorization is a domain policy
function over `(Actor, operation, subject)`.

*Why:* it is the rule `project.md` states and the reason the identity rules in
`add-mcp-read-server` were testable before an identity provider existed. Keeping it
means the entire authorization suite runs on constructed actors.

**Alternative rejected:** decorators on routers that check group names. Fast to
write, and it puts the identity provider's vocabulary in the inbound adapter, where
a later change to the group scheme becomes a change to every endpoint.

**Cost accepted:** the group-to-role mapping is configuration that must be kept
correct, and a mapping mistake is invisible until someone is refused. The specified
behaviour — unmapped groups grant nothing, a role-less actor resolves rather than
fails — makes that mistake safe and legible.

### D13 — Human-only operations are an explicit registry, checked in the application layer

Each mutating use case declares whether it requires a human actor. A test asserts
every mutating use case makes that declaration.

*Why:* `project.md` says promotion is never agent-callable, "not even for an art
director's agent", and `add-mcp-writes` will later add tools against these same use
cases. An absence cannot be enforced by absence — the same argument that made the
MCP tool list an exact-match test. Declaring it at the use case, not the adapter,
means it holds for every surface that ever calls it.

**Cost accepted:** one more thing to declare when adding a use case, and a test that
fails until you do. That is the desired ergonomics.

### D14 — Blobs are keyed by content digest and served by short-lived signed links, never proxied

The key is the digest of the bytes. The API issues a time-limited link to one
object after the authorization decision; it never streams bytes itself.

*Why:* a preview mesh or a concept view is megabytes, and proxying them through the
application would spend its request capacity on bandwidth. Content addressing makes
the mirror idempotent and makes re-mirroring after total loss produce identical keys
— which is what lets the recovery requirement be stated as "readable again under
the same keys".

**Alternative rejected:** proxying through the API, which makes authorization
trivially per-request and puts large transfers on the event loop.

**Cost accepted:** a signed link, once issued, is bearer access to that object until
it expires. The mitigation is the bound (short expiry, one object, no rewriting into
another key), and the acknowledgement that a link shared during its lifetime is
access shared — acceptable for concept art already visible to everyone who can read
the project, and the reason the expiry is configuration rather than a constant.

## Risks / Trade-offs

- **The HTTP adapter grows logic anyway** → the same structural test the MCP
  adapter has: `adapters/inbound/http/` imports nothing from `adapters/outbound/`
  and contains no conditional on specification content. Plus a cross-surface test
  that validates the same export through the CLI and the HTTP surface and asserts
  identical reports.
- **The configured branch is protected against direct pushes**, making D2
  unworkable at a studio that protects `main` → the branch is configuration, so the
  answer is a `canon` branch the studio merges on its own schedule. The specified
  behaviour does not change; only which ref is written.
- **The working copy grows unbounded** on a repository with large binary history →
  shallow, single-branch clones with a documented re-clone as the reclaim path.
  Recovery is already specified, so reclaiming disk is an operation that already
  exists.
- **A person edits in the tool while their teammate edits the same file in an
  editor** → D5 refuses one of them with the current content. Annoying, correct,
  and far better than either a silent overwrite or a merge nobody authored.
- **Staleness is reported and nobody reads it** → it is part of the response for
  every specification read, not a separate endpoint, so the surfaces built on top of
  this change inherit the obligation to show it. The UI decision belongs to the
  artist-facing changes; the data is not optional here.
- **The index rebuild is slow on a large project**, making the recovery guarantee
  technically true and operationally painful → rebuild is per project and resumable,
  and reads fall back to the working copy for the lookups the index would have
  answered. The guarantee is correctness; the speed is a tuning problem with a known
  shape.
- **Tenancy is derived from claims that CyberdyneAuth may not yet carry** → the
  mapping is configuration (D12), so a claim scheme that arrives later changes the
  adapter's configuration, not the domain or the specs.
- **Cost accepted overall:** this change makes CyberCanon a stateful, deployed
  system with a recovery procedure, in exchange for being usable by more than one
  person at a time. Every piece of that state — working copy, index, blob store — is
  specified as rebuildable from the remote repository, which is what keeps the
  bargain honest.

## Migration Plan

Additive. Changes 1–3 keep working unchanged: the CLI and MCP server still run
against a local working copy, still need no identity, and gain nothing they must
adopt. The one shared change is D10's result-union shape in the application layer,
which the CLI and MCP adapters adapt to in this change's task list.

Onboarding a project to the hosted surface is three steps, each individually
reversible: configure the repository URL, branch and credential; add
`.canon/actors.yaml` entries for the people who will write; point a webhook at the
API. A project that does none of these is unaffected.

Rollback is stopping the service. The repository keeps every commit the service
made — they are ordinary commits by ordinary authors — and nothing else the service
held was authoritative.

## Open Questions

- **Whether request files belong in the game repository or in a separate project
  repository.** They are repository content either way (D7); which repository is a
  configuration question a studio may want to answer differently when the game repo
  is heavily protected. It changes no specified behaviour.
- **The default fetch interval and the signed-link expiry.** Both are configuration
  governing behaviour that is already specified; the defaults want a real repository
  and a real network to choose well.
- **Whether tenancy comes from a claim or from project configuration** once
  CyberdyneAuth's organisation model is fixed. The specs require only that it come
  from verified claims when it comes from the credential at all.
- **How a project's discipline owners are declared** when an asset does not exist
  yet — project configuration is the obvious home, and `asset-requests` specifies
  the fallback behaviour without fixing the file.
