# Proposal

## Why

The original brief asked for a Game Design Document. Taken literally that means a
block editor, realtime collaborative editing, comments, version history and
export — months of work to arrive at a worse version of software this studio
already runs. **CyberArche is that software.** The honest answer to the GDD
requirement is therefore not to build one, but to *link* one, and to be precise
about which sentences belong on each side of the link.

That precision is the real content of this change. `project.md`'s golden rule says
a design field must constrain art, constrain code, or be checkable by the
validator. Everything that fails that test — why the scout mech reads as
scavenged, what the faction's silhouette language is trying to say, the argument
that settled the loadout — is exactly what long-form prose is *for*. Without a
sanctioned home, that prose has two bad destinations: it bloats `asset.yaml` with
wiki pages the validator cannot check, or it stays in Discord where nobody finds
it. Linking gives it a home and keeps the spec file mechanical.

The second half is search. `project.md` defers pgvector in CyberCanon on the
grounds that aliases plus full text plus **CyberArche's per-workspace RAG** cover
the need. That sentence is only true once the delegation exists — until then the
deferral is a gap, not a decision. This change makes it a decision: exact lookup
over ids, names and aliases stays local and deterministic, natural-language
questions about prose go to the system that already indexes prose.

It comes **after `add-web-backend`**, and it must. Delegated search forwards the
asking person's own bearer token so results are scoped to what that person may
read; there is no such token before auth integration exists. It comes **after
`add-mcp-read-server`**, because delegation is additive on top of a local exact
search that must already work — and must keep working when CyberArche is down.

## What Changes

- **Linked documents** — an asset or a project may carry references to long-form
  documents in CyberArche. The reference is authored content in the repository;
  the document stays where it lives and is **never mirrored here as a source of
  truth**.
- **Readable link display** — a stored reference resolves to a title and a short
  summary for display, fetched with the viewer's own credential and cached in the
  rebuildable index, so a link list reads as documents rather than as URLs.
- **Create-and-link** — creating a new, pre-titled document for an asset from
  inside CyberCanon, so writing the rationale for a spec is one action rather than
  a context switch plus a copy-pasted URL.
- **An explicit content boundary** — verifiable facts belong in the asset's
  `design` block, where they constrain art, constrain code and are checkable;
  prose rationale belongs in the document. The boundary is **one-way**: the design
  block is never generated, extracted or inferred from a linked document.
- **Semantic search delegated, exact search kept local** — a natural-language
  question is forwarded to CyberArche's per-workspace RAG; ids, names, aliases and
  tags continue to be answered by the local deterministic index. **No embeddings
  and no vector store enter CyberCanon.**
- **Results presented with provenance** — exact matches and semantic matches are
  shown as distinct, labelled groups with exact results first, so a probabilistic
  hit is never mistaken for a dictionary lookup.
- **Caller-scoped authority** — the asking person's bearer token is forwarded to
  CyberArche. A service credential is never used as end-user authority, and no
  CyberCanon specification content is pushed into a workspace the asker cannot
  read.
- **Degradation to absent** — with CyberArche unconfigured, unreachable or
  rejecting, every other capability behaves identically and linked-document
  features report themselves unavailable. Stored references remain visible as
  plain references.

## Capabilities

### New Capabilities

- `document-platform`: linking long-form documents to an asset or a project —
  what is stored, how a title and summary are resolved for display, opening and
  listing links, creating a pre-titled document, the behaviour when a document is
  unreachable, deleted or not permitted to the viewer, and the rule dividing
  checkable design facts from prose rationale.
- `semantic-search-delegation`: which query is answered locally and which is
  delegated, how the two result sets are presented together without implying the
  semantic ones are exact, what happens when the remote service is unavailable,
  and the authority and content-scoping rules that govern the delegated call.

### Modified Capabilities

None — no earlier change is archived yet, so a delta against an unarchived
capability cannot be written. Requirements that touch link storage, link display
in the compiled specification, and the presentation of search results are stated
inside `document-platform` and `semantic-search-delegation` instead.

## Non-goals

Explicitly **not** in this change:

- **No document editor.** No blocks, no realtime editing, no comment threads, no
  version history, no export. Every one of those is CyberArche's and stays there.
- **No mirroring of document content.** Nothing copies a document body into the
  repository, the index or a blob. There is no offline reading mode, and no sync.
- **No pgvector, no embeddings, no vector index in CyberCanon** — deferred by
  `project.md` and still deferred. Delegation is how that deferral is honoured,
  not a way around it.
- **No extraction from prose into the spec.** No importer, no model-backed pass
  that reads a document and fills `design` fields. The boundary is one-way by
  requirement.
- **No ingestion of CyberCanon content into CyberArche.** Compiled specifications
  are not pushed into a workspace to make them semantically searchable.
- **No new identity system.** Authority is the bearer token already established by
  `auth-integration`; this change forwards it and never mints authority of its own.
- **No cross-workspace or organisation-wide search.** A delegated query reaches
  exactly the workspaces the asking person can already read.
- **No change to validation.** `canon validate` still requires no identity and no
  network, and never contacts CyberArche.
- **No agent write path.** Nothing here lets an agent author a document, promote a
  rule, or edit a constraint. Whether an agent may *read* a linked document at all
  is left to `mcp-write-surface`'s successor changes to decide.

## Impact

- **New code** — `libs/cybercanon/domain/` (`DocumentRef`, `DocumentCard`,
  `DocumentState`, `ResultProvenance`, the content-placement rule);
  `libs/cybercanon/application/ports/doc_platform.py` (resolve, create, search)
  with an in-memory fake under `application/testing/`; use cases `link_document`,
  `unlink_document`, `list_linked_documents`, `create_document_for_asset`,
  `search_assets_and_docs`; `libs/cybercanon/adapters/outbound/arche/`.
- **New configuration** — `CANON_ARCHE_ENABLED` (default **false**),
  `CANON_ARCHE_BASE_URL`, `CANON_ARCHE_DEFAULT_WORKSPACE`,
  `CANON_ARCHE_TIMEOUT_S`. No credential of its own: the caller's token is
  forwarded.
- **Extended** — `asset.yaml`'s `links` gains structured document references
  alongside the plain URLs change 1 already stores; the rebuildable index gains a
  document-card table, dropped and rebuilt like everything else in it; the search
  response shape gains provenance grouping.
- **Consumer-side impact** — a game repo's specs may carry document references
  that render as titles in the web app and as a link line in the compiled
  `art-spec.md`. A deployment without CyberArche configured sees none of it and
  loses nothing else.
