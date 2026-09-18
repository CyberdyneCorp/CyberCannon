# Design

## Context

CyberCanon's whole argument is that a specification is valuable because it is
*mechanical*: every field constrains art, constrains code, or is checkable. Prose
is the opposite, and the tool has so far had nowhere to put it. CyberArche already
has the block editor, the CRDT session, the comment threads, the history and the
export — and a per-workspace retrieval index over exactly the kind of text
CyberCanon refuses to store.

So this change is mostly about **boundaries, not features**. Three of them decide
everything below:

1. Git is the source of truth. A link is authored content in the repository; a
   resolved title is cache.
2. The golden rule divides content: checkable facts here, rationale there, and the
   arrow never points back.
3. Authority belongs to the person. CyberArche enforces its own permissions, and
   CyberCanon's only correct behaviour is to ask *as the asker*.

`add-web-backend` supplies the bearer token and `auth-integration` the actor
resolution; `add-mcp-read-server` supplies the local deterministic index this
change refuses to replace. See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**

- Make the prose home official, findable, and impossible to confuse with the spec.
- Delegate semantic search so that `project.md`'s deferral of pgvector is a
  decision rather than a hole.
- Keep every path honest about which results are exact and which are guesses.
- Make the entire integration removable: unconfigure it and nothing else changes.

**Non-Goals (design level):**

- No offline reading of documents. There is no sync, so there is no sync design.
- No retrieval quality work. Ranking inside the retrieval service is its own
  concern; CyberCanon does not re-rank, blend or tune it.
- No caching strategy beyond a per-viewer display cache with a short lifetime.
- No fan-out to more than one document platform. One port, one adapter.

## Decisions

### D1 — `DocumentRef` is a domain value object stored in the spec; `DocumentCard` is cache

`DocumentRef(workspace, document_id, url, linked_by, linked_at)` is authored and
serialised into `asset.yaml` (or the project config). `DocumentCard(ref, title,
summary, state, resolved_at)` exists only in the rebuildable index and in memory.
`DocumentState` is the closed set `READABLE | UNREACHABLE | MISSING | FORBIDDEN`.

*Why:* it puts the durable/derived line exactly where `project.md` already puts it
for derived metadata — authored content in git, derived content in the disposable
index keyed for rebuild. **Alternative rejected:** storing the title in
`asset.yaml` next to the URL so link lists read well offline; rejected because a
rename at the source makes the repository wrong, and regenerating it churns the
diff and ruins `git blame` — the same argument that keeps generated descriptions
out of the spec. **Cost accepted:** a link list is unreadable when the platform is
down, so it renders addresses. That is the honest failure.

### D2 — The `DocumentPlatform` port takes the caller's credential per call

`DocumentPlatform.resolve(refs, credential)`, `.create(workspace, title,
credential)`, `.search(query, credential, budget)`. The credential is a parameter
on every method, never adapter construction state.

*Why:* the spec forbids a service credential standing in as end-user authority. If
the token lived in the adapter, every call would silently run as the service and
the permission model would be decorative. A parameter makes "whose authority is
this" unanswerable-by-omission — there is no call you can write without deciding.
**Alternative rejected:** a service token with an impersonation header, which is
how a single mis-set header becomes a workspace-wide leak. **Cost accepted:** no
background job can resolve cards, because background jobs have no end-user token.
Resolution therefore happens only on the read path, which bounds cache warmth to
who actually looked.

### D3 — The display cache is keyed by `(ref, actor)`, not by `ref`

A resolved card is stored against the actor who resolved it, with a short TTL, and
is never served to a different actor.

*Why:* a cache keyed by reference alone is a permission bypass with extra steps —
Rafa resolves a title, Bruno who cannot read that document sees it. Keying by
actor makes the leak structurally impossible rather than dependent on a check
nobody re-reads. **Alternative rejected:** a shared cache plus a per-read
permission probe, which is one round trip saved and one ordering bug away from the
leak. **Cost accepted:** cache hit rate divided by team size, and a cold resolve
for each person's first view. At a link list of single digits per asset, that is a
handful of requests.

### D4 — Availability is a null adapter chosen at composition, not a flag read at call sites

When `CANON_ARCHE_ENABLED` is false or configuration is incomplete, the container
wires a `NullDocumentPlatform` whose every method returns the unavailable outcome
with reason `unconfigured`. Use cases never branch on configuration.

*Why:* "degrades to absent" is specified for the whole integration, and the way
that requirement rots is fifteen scattered `if arche is None` checks, fourteen of
which are right. One wiring decision is testable once. It also matches the
`LLMPort` shape already established, so there is one degradation idiom in the
codebase rather than two. **Alternative rejected:** an optional dependency the use
cases check. **Cost accepted:** an extra class whose body is trivial.

### D5 — Search is local-first fan-out with a hard budget, and the local half never waits

`search_assets_and_docs` runs the local cascade to completion first, then makes at
most one delegated call bounded by `CANON_ARCHE_TIMEOUT_S`. On budget exhaustion
the local results are returned with the semantic group marked unavailable and
reason `timed_out`.

*Why:* the spec requires local search to survive the remote being unavailable, and
the only way to guarantee that is for the local answer to be complete before the
remote is asked. Ordering makes it a property, not a promise. **Alternative
rejected:** issuing both concurrently and joining — marginally faster, and it
makes "did the local half depend on the remote half" a question about scheduling.
**Cost accepted:** worst-case latency is local time plus the budget.

### D6 — Provenance is a field set by the producer; presentation groups, never merges

`SearchResult` carries `ResultProvenance.EXACT | SEMANTIC`. The local cascade
stamps `EXACT`; the adapter stamps `SEMANTIC`. Rendering groups by provenance with
exact first. There is no comparator that orders across groups.

*Why:* `semantic-search-delegation` requires that no ordering value rank a semantic
result against an exact one, and the cheapest way to satisfy that permanently is
for the comparison to be unwritable — there is no shared score to compare.
**Alternative rejected:** a unified score with a provenance penalty, which reads
as one ranked list and is exactly the confusion the requirement exists to prevent.

### D7 — Routing is a cheap syntactic gate, not a classifier

Delegation happens when the query produced no exact local hit **and** the query
looks like prose (contains whitespace, exceeds a small token count, is not a valid
identifier shape). Deterministic, inspectable, no model.

*Why:* the lookup path must never depend on a reachable model — `project.md` is
explicit. A syntactic gate is also debuggable: anyone can say why a query was or
was not delegated. **Alternative rejected:** an LLM intent classifier, which adds a
model dependency to the one path that must always work and turns a routing bug
into a prompt-tuning exercise. **Cost accepted:** a prose-shaped query that also
matches an alias exactly is not delegated, so the person re-phrases. Those cases
show up in the local miss log and can move the gate later.

### D8 — Create-and-link commits in that order, and an orphan document beats a dangling link

`create_document_for_asset` creates remotely, then writes the reference through
`SpecStore`. A failure after creation reports the created document's address in
the error.

*Why:* the reverse order would put a reference to a non-existent document into the
repository, where git preserves it forever and every future viewer sees a broken
link. An orphan untitled document in a workspace is visible, harmless and
deletable by its creator. **Alternative rejected:** a two-phase reservation
protocol, which needs a remote feature CyberArche has no reason to offer.
**Cost accepted:** rare orphan documents, named in the failure message so the
person can delete or re-link them.

### D9 — The content boundary is one-way by construction: there is no read path from document to spec

No use case accepts a document body. The `DocumentPlatform` port returns titles,
summaries and search passages, and has no method returning a full document. The
spec-editing use cases have no parameter that could carry extracted content.

*Why:* "the design block is never generated from the document" is a rule that is
enforced by nothing if the body is reachable — someone eventually adds a helpful
"pre-fill from doc" button. Not exposing the body makes the temptation
unimplementable without a port change that shows up in review. **Alternative
rejected:** a documented convention. **Cost accepted:** a genuinely useful future
feature — a person-driven "quote this passage into the spec" — would require
widening the port deliberately, which is the point.

### D10 — Nothing is ever pushed to CyberArche; the adapter is a query client

The adapter has no write path other than `create` (an empty pre-titled document).
It never uploads specifications, annotations or compiled briefings.

*Why:* CyberCanon does not control workspace membership, so any content it pushed
would be governed by permissions it cannot see. **Alternative rejected:**
mirroring compiled `art-spec.md` into a workspace so specs become semantically
searchable; rejected because it publishes canon into a permission domain we do not
own, and because the compiled spec is already exactly searchable where it lives.

### D11 — What stays in the domain, what belongs to the adapter

**Domain:** `DocumentRef` well-formedness, `DocumentState`, `ResultProvenance`,
the ordering rule (exact before semantic), the content-placement rule, and the
decision that a `FORBIDDEN` card discloses nothing.

**Application:** the `DocumentPlatform` port, the use cases `link_document`,
`unlink_document`, `list_linked_documents`, `create_document_for_asset`,
`search_assets_and_docs`, the routing gate, the fan-out ordering and the budget.

**Adapter (`adapters/outbound/arche/`):** HTTP, CyberArche's URL shapes, workspace
identifiers, the bearer header, retrieval request and response payloads, mapping
transport failures onto `DocumentState` and the unavailability reasons. No domain
object knows CyberArche exists by name.

## Risks / Trade-offs

- **A cached card leaks to someone who may not see the document** → D3 keys the
  cache by actor; a test resolves as one actor and asserts a second actor gets a
  cold resolve and a `FORBIDDEN` card.
- **Semantic results get read as canon** → D6's grouping plus a label on every
  semantic passage naming its source document and stating it is approximate. The
  cheap version of this mistake — a passage quoted as a constraint — is the one the
  product exists to prevent.
- **The prose home becomes the real spec**, with people writing budgets into
  documents because it is easier than editing YAML → mitigated by requirement
  (document contents are not constraints, and validation ignores them) and by
  guidance at the point of authoring. Ultimately social; the validator is the
  enforcement, as everywhere else in this product.
- **Token forwarding couples search latency to CyberArche's auth path** → D5's hard
  budget, and the local half already being complete before the call is made.
- **CyberArche's retrieval API changes shape** → confined to one adapter; the port
  returns passages with a document reference and nothing structural about
  retrieval.
- **Cost accepted:** documents are unreadable in the link list when the platform is
  down, and search silently narrows to exact matches. Both are visible states, not
  silent ones, which is the trade we want: a degraded answer that says it is
  degraded.

## Migration Plan

Additive and reversible. Existing plain URLs in `links` continue to work untouched;
a structured document reference is a new, optional shape alongside them, and the
linter accepts both. A deployment that never sets `CANON_ARCHE_ENABLED` behaves
exactly as before — the null adapter is the default wiring. The document-card table
is part of the rebuildable index and is dropped and rebuilt with it.

Rollback is unsetting the configuration: references remain in the repository as
addresses, and every other capability is unaffected. Nothing in this change
requires a data migration, because nothing in it is durable outside git.

## Open Questions

- **Whether a document link should carry a declared kind** (`gdd`, `rationale`,
  `research`) for filtering. It adds a field to the reference and changes no
  behaviour specified here; deferred until there are enough links per asset for
  filtering to be worth anything.
- **Whether an agent may read a linked document's summary over MCP.** It is a read,
  so it does not violate the write prohibition, but it widens what a local agent
  process can pull from a permissioned workspace. Left to the change that owns the
  MCP write surface and its successors.
- **The display cache TTL.** A configuration value; the behaviour it governs —
  per-actor keying and re-resolution on view — is already specified.
