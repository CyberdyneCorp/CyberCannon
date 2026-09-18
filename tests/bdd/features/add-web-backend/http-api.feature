# Generated from openspec/changes/add-web-backend/specs/http-api/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-backend @capability:http-api @spec:openspec/changes/add-web-backend/specs/http-api/spec.md
Feature: http-api

  Rule: The surface is a thin adapter over shared use cases

    Scenario: Validation agrees across surfaces
      Given an export that fails its triangle budget
      When it is validated over HTTP and again from the command line
      Then both SHALL report the same violations with the same severities and the same overall outcome

    Scenario: Compilation agrees across surfaces
      Given an asset whose specification compiles to a briefing
      When the briefing is requested over HTTP and produced from the command line at the same repository revision
      Then both SHALL be identical

    Scenario: Lookup agrees across surfaces
      Given a query matching several assets
      When it is issued over HTTP and through the agent surface at the same repository revision
      Then both SHALL return the same assets in the same order

  Rule: Resources are addressed by stable, project-scoped identifiers

    Scenario: Address survives an index rebuild
      Given a resource reachable at a given address
      When the index is dropped and rebuilt from the repository
      Then the resource SHALL be reachable at the same address

    Scenario: Unknown identifier is not found
      When a resource is requested with an identifier no specification declares
      Then the response SHALL report that it does not exist

  Rule: Domain outcomes map to status codes by a single fixed mapping

    Scenario: A domain refusal is not an internal error
      Given an operation the domain refuses because the actor lacks the required role
      When it is requested over HTTP
      Then the response SHALL report a refusal naming the required role
      And SHALL NOT report an internal failure

    Scenario: The same outcome maps identically everywhere
      Given two different endpoints that can both produce a not-found outcome
      When each produces it
      Then both SHALL return the same status class and the same error shape

    Scenario: Error bodies are machine-readable and specific
      When any request fails
      Then the response body SHALL carry a stable machine-readable error identifier, a human-readable message, and the subject at fault where one exists

  Rule: Unexpected failures are reported without leaking internals

    Scenario: Correlated generic failure
      Given an outbound dependency raises an unexpected error
      When a request encounters it
      Then the response SHALL report a generic failure with a correlation identifier
      And SHALL NOT contain a stack trace or any configuration value

  Rule: Listings are paginated with stable ordering

    Scenario: Full traversal returns each result once
      Given a listing of results larger than one page and a data set that does not change during traversal
      When the caller follows continuation tokens to exhaustion
      Then every result SHALL appear exactly once

    Scenario: Oversized page request is bounded
      When a caller requests a page larger than the maximum
      Then the response SHALL return at most the maximum page size

    Scenario: A continuation token grants nothing
      Given a continuation token issued to an actor permitted to read a project
      When it is presented by an actor not permitted to read that project
      Then the request SHALL be refused

  Rule: State-changing requests are idempotent by key

    Scenario: Replay returns the original outcome
      Given a state-changing request that succeeded with a given idempotency key
      When the identical request is sent again with the same key
      Then the response SHALL describe the original outcome
      And no second change SHALL be applied

    Scenario: Reused key with different content is refused
      Given an idempotency key already used for one request body
      When a different request body is sent with that key
      Then the request SHALL be refused as conflicting

    Scenario: A retried write creates one commit
      Given a write that was applied but whose response was lost in transit
      When the caller retries it with the same idempotency key
      Then the repository SHALL contain exactly one commit for that edit

  Rule: Writes declare the revision they were based on

    Scenario: Stale write is refused
      Given a caller composed an edit against a revision that has since changed
      When the edit is submitted
      Then it SHALL be refused as conflicting
      And the response SHALL name the current revision
      And the stored content SHALL be unchanged

    Scenario: Missing revision is refused
      When a specification-modifying request omits the revision it was based on
      Then it SHALL be rejected as invalid

  Rule: The surface is explicitly versioned and evolves additively

    Scenario: Unknown optional field is tolerated
      Given a client written against the current version
      When the surface adds an optional response field
      Then the client's requests SHALL continue to succeed

    Scenario: Unversioned request is rejected
      When a request is made without an identifiable surface version
      Then it SHALL be rejected as invalid rather than served by a guessed version

  Rule: Actions reserved to people are refused to automated callers

    Scenario: Service credential cannot promote
      Given a caller authenticated with a service credential holding every role
      When it attempts to promote an annotation to a durable rule
      Then the attempt SHALL be refused as requiring a person

    Scenario: Human-only actions are enumerated, not incidental
      When the set of operations refused to automated callers is inspected
      Then it SHALL be an explicit enumeration, so that adding an operation to the surface does not silently make it available to automation

  Rule: Health reporting does not depend on optional or sibling services

    Scenario: Healthy while optional services are down
      Given the language model endpoint and the document platform are unreachable
      When the health report is requested
      Then it SHALL report the process as able to serve requests
      And SHALL describe those dependencies as unavailable

    Scenario: Health does not require identity
      Given the identity service is unreachable
      When the health report is requested
      Then it SHALL succeed
