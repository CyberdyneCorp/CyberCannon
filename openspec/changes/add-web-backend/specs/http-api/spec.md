# Spec Delta

## Purpose

Defines the networked surface through which several people reach one project's
canon — how resources are addressed, how domain outcomes become status codes, how
listings page, how a repeated request stays safe, and the rule that this surface
decides nothing the command line and the agent surface do not already decide.

## ADDED Requirements

### Requirement: The surface is a thin adapter over shared use cases

Every operation exposed over HTTP SHALL be served by invoking the same application
use case that serves the equivalent command-line and agent operation. The surface
SHALL NOT contain its own implementation of validation rules, specification
compilation, effective-value merging, lookup ranking or status transitions.

#### Scenario: Validation agrees across surfaces
- **GIVEN** an export that fails its triangle budget
- **WHEN** it is validated over HTTP and again from the command line
- **THEN** both SHALL report the same violations with the same severities and the
  same overall outcome

#### Scenario: Compilation agrees across surfaces
- **GIVEN** an asset whose specification compiles to a briefing
- **WHEN** the briefing is requested over HTTP and produced from the command line
  at the same repository revision
- **THEN** both SHALL be identical

#### Scenario: Lookup agrees across surfaces
- **GIVEN** a query matching several assets
- **WHEN** it is issued over HTTP and through the agent surface at the same
  repository revision
- **THEN** both SHALL return the same assets in the same order

### Requirement: Resources are addressed by stable, project-scoped identifiers

Every addressable resource SHALL be identified by a project identifier and the
identifier the specification already uses for that resource, and SHALL remain
reachable at that address for as long as the resource exists. The surface SHALL
NOT address a resource by a database-generated key, and an address SHALL NOT
change because the index was rebuilt.

#### Scenario: Address survives an index rebuild
- **GIVEN** a resource reachable at a given address
- **WHEN** the index is dropped and rebuilt from the repository
- **THEN** the resource SHALL be reachable at the same address

#### Scenario: Unknown identifier is not found
- **WHEN** a resource is requested with an identifier no specification declares
- **THEN** the response SHALL report that it does not exist

### Requirement: Domain outcomes map to status codes by a single fixed mapping

Each outcome the domain can express — not found, refused for lack of permission,
refused because the caller is unidentified, rejected as invalid input, refused
because the resource changed since it was read, and refused because a precondition
of the domain is unmet — SHALL map to exactly one status class, through one
mapping used by every endpoint. An outcome the domain expressed SHALL NOT be
reported as an unexpected internal failure.

#### Scenario: A domain refusal is not an internal error
- **GIVEN** an operation the domain refuses because the actor lacks the required
  role
- **WHEN** it is requested over HTTP
- **THEN** the response SHALL report a refusal naming the required role
- **AND** SHALL NOT report an internal failure

#### Scenario: The same outcome maps identically everywhere
- **GIVEN** two different endpoints that can both produce a not-found outcome
- **WHEN** each produces it
- **THEN** both SHALL return the same status class and the same error shape

#### Scenario: Error bodies are machine-readable and specific
- **WHEN** any request fails
- **THEN** the response body SHALL carry a stable machine-readable error
  identifier, a human-readable message, and the subject at fault where one exists

### Requirement: Unexpected failures are reported without leaking internals

When an operation fails for a reason the domain did not express, the surface SHALL
report a generic failure carrying a correlation identifier, and SHALL NOT include
a stack trace, a file system path, a connection string, a credential, or the
content of a configuration value in the response.

#### Scenario: Correlated generic failure
- **GIVEN** an outbound dependency raises an unexpected error
- **WHEN** a request encounters it
- **THEN** the response SHALL report a generic failure with a correlation identifier
- **AND** SHALL NOT contain a stack trace or any configuration value

### Requirement: Listings are paginated with stable ordering

Every listing endpoint SHALL return results in a deterministic total order, SHALL
apply a default and a maximum page size, and SHALL provide an opaque continuation
token when more results exist. Paging through an unchanged data set SHALL return
each result exactly once, and a continuation token SHALL NOT be interpretable as a
filter or an authorization grant.

#### Scenario: Full traversal returns each result once
- **GIVEN** a listing of results larger than one page and a data set that does not
  change during traversal
- **WHEN** the caller follows continuation tokens to exhaustion
- **THEN** every result SHALL appear exactly once

#### Scenario: Oversized page request is bounded
- **WHEN** a caller requests a page larger than the maximum
- **THEN** the response SHALL return at most the maximum page size

#### Scenario: A continuation token grants nothing
- **GIVEN** a continuation token issued to an actor permitted to read a project
- **WHEN** it is presented by an actor not permitted to read that project
- **THEN** the request SHALL be refused

### Requirement: State-changing requests are idempotent by key

A state-changing request MAY carry a caller-supplied idempotency key. When a key
is repeated for the same operation and the same actor, the surface SHALL return
the outcome of the original request and SHALL NOT apply the change a second time.
When a key is repeated with a different request body, the surface SHALL refuse the
request rather than apply either interpretation.

#### Scenario: Replay returns the original outcome
- **GIVEN** a state-changing request that succeeded with a given idempotency key
- **WHEN** the identical request is sent again with the same key
- **THEN** the response SHALL describe the original outcome
- **AND** no second change SHALL be applied

#### Scenario: Reused key with different content is refused
- **GIVEN** an idempotency key already used for one request body
- **WHEN** a different request body is sent with that key
- **THEN** the request SHALL be refused as conflicting

#### Scenario: A retried write creates one commit
- **GIVEN** a write that was applied but whose response was lost in transit
- **WHEN** the caller retries it with the same idempotency key
- **THEN** the repository SHALL contain exactly one commit for that edit

### Requirement: Writes declare the revision they were based on

A request that modifies specification content SHALL carry the revision identifier
of the content it was composed against. When that content has changed since,
the surface SHALL refuse the write, report the conflict, and return the current
revision, and SHALL NOT apply the change.

#### Scenario: Stale write is refused
- **GIVEN** a caller composed an edit against a revision that has since changed
- **WHEN** the edit is submitted
- **THEN** it SHALL be refused as conflicting
- **AND** the response SHALL name the current revision
- **AND** the stored content SHALL be unchanged

#### Scenario: Missing revision is refused
- **WHEN** a specification-modifying request omits the revision it was based on
- **THEN** it SHALL be rejected as invalid

### Requirement: The surface is explicitly versioned and evolves additively

The HTTP surface SHALL carry an explicit version, and within a version the surface
SHALL only add optional fields, endpoints and enumerated values. Removing a field,
renaming a field, narrowing an accepted value, or changing the meaning of an
existing field SHALL require a new version, and a client written against a version
SHALL keep working while that version is served.

#### Scenario: Unknown optional field is tolerated
- **GIVEN** a client written against the current version
- **WHEN** the surface adds an optional response field
- **THEN** the client's requests SHALL continue to succeed

#### Scenario: Unversioned request is rejected
- **WHEN** a request is made without an identifiable surface version
- **THEN** it SHALL be rejected as invalid rather than served by a guessed version

### Requirement: Actions reserved to people are refused to automated callers

An operation the project defines as a human action — including promoting an
annotation to a durable rule, accepting a derived suggestion, and deciding an
asset request — SHALL be refused when the caller is a service credential or an
automated caller, regardless of the roles held. The refusal SHALL state that the
action requires a person.

#### Scenario: Service credential cannot promote
- **GIVEN** a caller authenticated with a service credential holding every role
- **WHEN** it attempts to promote an annotation to a durable rule
- **THEN** the attempt SHALL be refused as requiring a person

#### Scenario: Human-only actions are enumerated, not incidental
- **WHEN** the set of operations refused to automated callers is inspected
- **THEN** it SHALL be an explicit enumeration, so that adding an operation to the
  surface does not silently make it available to automation

### Requirement: Health reporting does not depend on optional or sibling services

The surface SHALL expose the liveness and readiness signals specified by the
`deployment-operations` capability, which owns their shape and semantics; this
capability SHALL NOT define a separate or additional health surface. Its readiness
signal SHALL NOT require a language model endpoint, the identity service, the
document platform, the rebuildable index, or any sibling backend to be reachable,
and SHALL separately describe the state of each dependency it observes, so that a
degraded dependency is visible without withholding traffic.

#### Scenario: Healthy while optional services are down
- **GIVEN** the language model endpoint and the document platform are unreachable
- **WHEN** the health report is requested
- **THEN** it SHALL report the process as able to serve requests
- **AND** SHALL describe those dependencies as unavailable

#### Scenario: Health does not require identity
- **GIVEN** the identity service is unreachable
- **WHEN** the health report is requested
- **THEN** it SHALL succeed
