# Tasks

## 1. Domain — actor, authorization, attribution

- [ ] 1.1 Model `ActorId`, `Actor` (id, display name, roles, projects) and `Role` (`ART_DIRECTOR | ARTIST | DESIGNER | ENGINEER`) as frozen value objects; verify `lint-imports` still reports zero third-party imports in the domain
- [ ] 1.2 Implement the read-entitlement policy (may this actor read this project) as a pure function and verify tests cover entitled, unentitled and local-actor cases with no identity service present
- [ ] 1.3 Implement `Attribution(actor, via)` with a non-optional actor (D5) and verify a test asserts no constructor path produces an attribution without an actor
- [ ] 1.4 Implement the rule that automated callers may not author durable content, as a policy function, and verify it refuses for every role in turn
- [ ] 1.5 Model `GitAuthor`, `ActorBinding` (subject, display name, git emails, chat handle, default role) and `ActorMapping` as frozen value objects, plus an unmapped `Actor` carrying the raw email and no roles (D14); verify `lint-imports` still reports zero third-party imports in the domain
- [ ] 1.6 Implement resolution in both directions as pure functions over `ActorMapping` (D12) and verify case-insensitive email matching, an actor with several emails yielding the first for commits, and a round trip returning the original actor
- [ ] 1.7 Verify the unmapped path: a test asserts an unmatched email returns an unmapped actor carrying that email, that a near-miss email is never resolved to the similar mapped actor, and that no resolution signature can return nothing
- [ ] 1.8 Implement structural mapping rules — duplicate subject, duplicate email across entries, default role outside the role set, entry with no email, unparseable mapping — returning `Violation` values in the existing report shape; verify each defect is reported naming the offending entry

## 2. Application — identity resolution and ports

- [ ] 2.1 Define the `IdentityProvider` port returning a resolved `Actor` from a credential, and verify a fake provider satisfies a port-conformance test
- [ ] 2.2 Implement the resolution chain — configured credential → cached actor with TTL → local unauthenticated read-only actor (D4) — and verify each link is selected under the expected conditions
- [ ] 2.3 Verify degradation: a test where the provider raises proves reads still succeed via the cached actor, and a test with an expired cached actor proves role-requiring actions are refused as unverifiable
- [ ] 2.4 Verify no tool parameter can influence identity: a test supplying actor and role parameters asserts the resolved actor is unchanged
- [ ] 2.5 Define the `SearchIndex` port (upsert asset, lookup by id, list with filters, ranked search, record miss, list misses, staleness check) with an in-memory fake under `application/testing/`
- [ ] 2.6 Extend the `SpecStore` port with history access (read a spec file at an earlier revision) and verify the fake supports a revision series
- [ ] 2.7 Extend the `SpecStore` port with a project-scoped read for the actor mapping (D12) and verify the fake serves a mapping, an absent mapping as empty, and an unparseable one as a violation rather than an exception
- [ ] 2.8 Implement the precedence chain — provider claims → mapping file → unmapped actor (D13) — and verify each link is selected under the expected conditions, including that the file is not consulted when the provider supplies git emails
- [ ] 2.9 Verify disagreement handling: a test where the provider and the file bind the same subject to different emails asserts the provider's values are used and a violation reports the file entry
- [ ] 2.10 Implement retrieval of a project's distinct unmapped authors and verify it lists each unmatched email once

## 3. Application — lookup and lens use cases

- [ ] 3.1 Implement `rebuild_index` scanning the repository for specification files and verify it reports indexed count and names unreadable files without aborting
- [ ] 3.2 Implement per-file staleness detection by mtime and size with self-healing re-read on the read path (D8) and verify an edited spec is served current without a full rebuild
- [ ] 3.3 Verify the index is disposable: a test deletes the index, rebuilds, and asserts every lookup and search result is identical to before
- [ ] 3.4 Implement `where_is` returning directory, source file, latest validated export with its validation date, engine path, links, status and the three owners; verify unrecorded locations are reported as absent rather than omitted
- [ ] 3.5 Implement `list_assets` with status, owner and tag filters scoped to a project, and verify combined filters
- [ ] 3.6 Implement `search_assets` as the fixed five-pass cascade (D9) and verify exact-id outranks description substring, alias matching works, and results are deterministic across runs
- [ ] 3.7 Implement zero-result query logging to a local file and a retrieval command (D11); verify a miss is recorded, a hit is not, and nothing is transmitted off the machine
- [ ] 3.8 Implement `compile_spec_for_lens` as a projection over the single compiled specification (D2) and verify a field common to two lenses is byte-identical in both
- [ ] 3.9 Verify lens behavior: `modeling` contains required sockets and omits the palette, an absent lens returns everything, an unknown lens is refused naming the valid set, and no lens exposes resolved or promoted annotations
- [ ] 3.10 Verify lens ordering (D3): a test asserts authorization is evaluated before the lens is applied, and that an unentitled read is refused identically under every lens
- [ ] 3.11 Implement `diff_spec` comparing parsed specifications field by field into semantic statements (D10) and verify a budget change renders as previous → current, an unchanged spec says so, and missing history degrades with a message instead of failing
- [ ] 3.12 Resolve every owner, author and responsible person through the mapping before rendering, in `where_is` and in every listing that names an owner; verify a mapped owner renders as the display name, an unmapped one renders as the raw email marked unmapped, and one person appearing as owner, commit author and caller renders identically in all three

## 4. Adapters — index and history

- [ ] 4.1 Implement `SqliteSearchIndex` with FTS5 over ids, names, aliases, tags and descriptions in a git-ignored file under `.canon/` (D7) and verify it passes the same port-conformance suite as the in-memory fake
- [ ] 4.2 Extend `GitSpecStore` with revision history reading and verify it returns an earlier revision of a spec file, and reports unavailability on a repository without the requested history
- [ ] 4.3 Add `.canon/index.sqlite` and the query log to `.gitignore` and verify a full validate-index-search cycle leaves the working tree clean
- [ ] 4.4 Implement reading `.canon/actors.yaml` in `GitSpecStore` at the same revision as the specification files, and verify an absent file yields an empty mapping with no failure and a malformed file yields a violation naming the file
- [ ] 4.5 Extend the `IdentityProvider` adapter contract so a provider MAY supply git author emails for a resolved actor, and verify a fake provider that supplies them and one that does not both satisfy the port-conformance test

## 5. Adapters — MCP inbound

- [ ] 5.1 Implement the FastMCP stdio server exposing `where_is`, `list_assets`, `search_assets`, `get_asset_spec`, `get_constraints`, `get_open_annotations`, `diff_spec` and `validate_export`; verify a client lists exactly these tools
- [ ] 5.2 Implement prose renderers (compact tables for listings, markdown for specifications) and verify assertions on content rather than exact wording, including that a lensed response names the lens used and states a full specification exists
- [ ] 5.3 Wire `validate_export` to the existing use case and verify a test asserts the MCP result and the CLI result are identical for the same export
- [ ] 5.4 Implement legible failures — unknown asset returns nearest matches, malformed spec is reported separately while other assets still list, and no recoverable error ends the session; verify each case
- [ ] 5.5 Add the D1 structural test asserting the MCP adapter contains no conditional on specification content and imports nothing from `adapters/outbound/`
- [ ] 5.6 Add the D6 tool-surface tests: the advertised tool-name set matches an exact expected list, and running every tool against a clean working tree leaves it clean
- [ ] 5.7 Verify the promotion prohibition explicitly: a test asserts no promotion tool exists and that a caller acting as an art director is refused

## 6. CLI, wiring and acceptance

- [ ] 6.1 Add `canon mcp serve` launching the server for a project directory, and verify via subprocess that it completes a `where_is` call with no credential configured
- [ ] 6.2 Add `canon index rebuild` and `canon index misses` and verify their reported counts and malformed-file names
- [ ] 6.3 Wire mapping validation into the existing lint path and add a command listing a project's unmapped authors; verify a repository with a duplicate email exits non-zero naming both entries, and that both run with no network and no credential
- [ ] 6.4 Extend the composition root to build both inbound adapters from one container (D11 of change 1) and verify a test resolves every use case for both surfaces
- [ ] 6.5 Verify offline operation end to end: a subprocess test with all network access denied completes `where_is`, `get_asset_spec`, `search_assets` and `validate_export`
- [ ] 6.6 Document agent client configuration and add the `CLAUDE.md` snippet telling repo-reading agents that specifications exist and where; verify the documented command string launches the server
- [ ] 6.7 Run the identity-mapping acceptance test on a repository with real history: every mapped git author is reported as the person wherever a name appears, every unmapped author is reported as unmapped and listed for completion, and no name resolves to the wrong person
- [ ] 6.8 Run the acceptance test: a developer's agent answers "where do I get the mech scout model and what must it satisfy" using only MCP tools, with no human asked; record any question it could not answer as a candidate gap
- [ ] 6.9 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check, and confirm the backend target of 15 per function holds
