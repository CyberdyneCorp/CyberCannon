# Spec Delta

## Purpose

Splits search into two honest halves: exact lookup over asset identifiers, names
and aliases stays local and deterministic, while natural-language questions about
long-form prose are delegated to the document platform's per-workspace retrieval,
with the asker's own authority and without either half depending on the other.

## ADDED Requirements

### Requirement: Exact lookup is always local and deterministic

Lookup over asset identifiers, names, aliases, tags, status and owners SHALL be
answered from the local index without contacting any remote service. The same
query against the same repository content SHALL return the same results in the
same order on every run. The system SHALL NOT compute, store or query vector
embeddings for this purpose.

#### Scenario: Repeated query is stable
- **GIVEN** a repository whose specifications have not changed
- **WHEN** the same query is run twice
- **THEN** both runs SHALL return identical results in identical order

#### Scenario: Exact lookup needs no remote service
- **GIVEN** the document platform is unreachable
- **WHEN** an asset is searched by identifier, name, alias or tag
- **THEN** the result SHALL be returned normally

#### Scenario: Identifier query is never answered only semantically
- **GIVEN** a query that exactly matches an asset identifier or alias
- **WHEN** the search runs
- **THEN** that asset SHALL appear in the exact results
- **AND** it SHALL NOT be omitted in favour of a semantically retrieved result

### Requirement: Prose questions are delegated, and delegation is additive

A query that does not resolve to an exact identifier, name, alias or tag, and that
is shaped as natural language rather than an identifier, SHALL additionally be
forwarded to the document platform's retrieval service, scoped to the workspaces
the asking person can read. Delegation SHALL NOT replace the local search: local
results SHALL be produced for every query regardless of whether delegation occurs
or succeeds.

#### Scenario: Natural-language question reaches the document platform
- **GIVEN** the query "why does the scout mech look scavenged"
- **WHEN** the search runs with the document platform configured
- **THEN** the query SHALL be forwarded to the retrieval service
- **AND** any passages it returns SHALL be included in the response

#### Scenario: Local results are produced either way
- **GIVEN** any query
- **WHEN** the search runs
- **THEN** the local index SHALL be consulted
- **AND** its results SHALL be present in the response

#### Scenario: Identifier-shaped query is not delegated
- **GIVEN** the query `mech_scout`
- **WHEN** it matches an asset identifier in the local index
- **THEN** no query SHALL be forwarded to the retrieval service

### Requirement: Results are presented with provenance, exact first

Every result SHALL carry its provenance, stating whether it is an exact match from
the local index or a semantically retrieved passage. The two SHALL be presented as
distinct labelled groups with exact matches ordered before semantic ones, and
SHALL NOT be merged into a single ranking or a single relevance score. Each
semantic result SHALL name the document it came from and SHALL be labelled as an
approximate match rather than a definitive answer.

#### Scenario: Groups are labelled and ordered
- **GIVEN** a query producing both exact and semantic results
- **WHEN** the response is rendered
- **THEN** exact matches SHALL appear first under a label identifying them as
  exact
- **AND** semantic matches SHALL appear after, labelled as approximate

#### Scenario: Semantic results name their source
- **WHEN** a semantically retrieved passage is presented
- **THEN** it SHALL name the document it came from
- **AND** it SHALL be openable at the document platform

#### Scenario: No combined score
- **WHEN** a response containing both kinds of result is inspected
- **THEN** no ordering value SHALL rank a semantic result against an exact one

#### Scenario: A semantic hit is not an asset record
- **GIVEN** a semantic result mentioning an asset by name
- **WHEN** the response is presented
- **THEN** it SHALL NOT be presented as that asset's specification or location
- **AND** the asset's own record SHALL be reachable only through the exact results

### Requirement: The asking person's authority is forwarded

A delegated query SHALL be made with the credential presented by the asking person
and SHALL return only what that person is permitted to read at the document
platform. The system SHALL NOT substitute a service credential, a shared account
or any credential of its own as the authority for a person's query, and SHALL NOT
accept an identity supplied as a query parameter.

#### Scenario: Two people get different results
- **GIVEN** two people with access to different workspaces
- **WHEN** each runs the same natural-language query
- **THEN** each SHALL receive only passages from workspaces they may read

#### Scenario: Service credential is never end-user authority
- **WHEN** a delegated query is made on behalf of a person
- **THEN** the credential presented to the retrieval service SHALL be that person's
- **AND** no query SHALL be made under a service credential on a person's behalf

#### Scenario: No forwardable credential means local only
- **GIVEN** a caller with no forwardable credential
- **WHEN** a natural-language query is run
- **THEN** only local results SHALL be returned
- **AND** the semantic portion SHALL be reported as unavailable for lack of
  authority

### Requirement: No specification content is ingested into the document platform

The system SHALL NOT transmit specifications, compiled specifications,
annotations, exports or any other repository content to the document platform for
indexing, storage or retrieval. The only content transmitted in a delegated query
SHALL be the query text and the scope required to route it.

#### Scenario: Only the query is sent
- **WHEN** a natural-language query is delegated
- **THEN** the transmitted payload SHALL contain the query text and routing scope
- **AND** it SHALL contain no specification or annotation content

#### Scenario: No indexing path exists
- **WHEN** the system's operations are enumerated
- **THEN** none SHALL push repository content into a document platform workspace

### Requirement: Local search survives the retrieval service being unavailable

When the document platform is unconfigured, unreachable, rejects the credential,
exceeds the configured time budget, or returns a malformed response, the search
SHALL still return its local results, SHALL report the semantic portion as
unavailable with the distinguishing reason, and SHALL NOT fail as a whole.

#### Scenario: Unreachable service degrades the response, not the search
- **GIVEN** the retrieval service is unreachable
- **WHEN** a natural-language query is run
- **THEN** the local results SHALL be returned
- **AND** the response SHALL state that semantic results were unavailable and why

#### Scenario: Slow service does not hold the response
- **GIVEN** a retrieval service that does not answer within the configured time
  budget
- **WHEN** a query is run
- **THEN** the response SHALL be returned within that budget plus the local search
  time
- **AND** the semantic portion SHALL be reported as unavailable

#### Scenario: Reason is distinguishable
- **WHEN** semantic results are unavailable
- **THEN** the reported reason SHALL distinguish at least unconfigured,
  unreachable, rejected and timed out

### Requirement: Unanswered queries are recorded locally

A query returning no exact results SHALL be recorded as a local miss, as specified
by `asset-lookup`, whether or not semantic results were returned for it. The
record SHALL remain on the machine that made it and SHALL NOT be transmitted to
the document platform or anywhere else.

#### Scenario: A semantic hit does not hide an exact miss
- **GIVEN** a query with no exact results but two semantic results
- **WHEN** the search completes
- **THEN** the query SHALL be recorded as a miss

#### Scenario: Misses stay local
- **WHEN** a miss is recorded
- **THEN** no request carrying it SHALL be made to any remote service
