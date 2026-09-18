# Generated from openspec/changes/add-cyberarche-integration/specs/semantic-search-delegation/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-cyberarche-integration @capability:semantic-search-delegation @spec:openspec/changes/add-cyberarche-integration/specs/semantic-search-delegation/spec.md
Feature: semantic-search-delegation

  Rule: Exact lookup is always local and deterministic

    Scenario: Repeated query is stable
      Given a repository whose specifications have not changed
      When the same query is run twice
      Then both runs SHALL return identical results in identical order

    Scenario: Exact lookup needs no remote service
      Given the document platform is unreachable
      When an asset is searched by identifier, name, alias or tag
      Then the result SHALL be returned normally

    Scenario: Identifier query is never answered only semantically
      Given a query that exactly matches an asset identifier or alias
      When the search runs
      Then that asset SHALL appear in the exact results
      And it SHALL NOT be omitted in favour of a semantically retrieved result

  Rule: Prose questions are delegated, and delegation is additive

    Scenario: Natural-language question reaches the document platform
      Given the query "why does the scout mech look scavenged"
      When the search runs with the document platform configured
      Then the query SHALL be forwarded to the retrieval service
      And any passages it returns SHALL be included in the response

    Scenario: Local results are produced either way
      Given any query
      When the search runs
      Then the local index SHALL be consulted
      And its results SHALL be present in the response

    Scenario: Identifier-shaped query is not delegated
      Given the query `mech_scout`
      When it matches an asset identifier in the local index
      Then no query SHALL be forwarded to the retrieval service

  Rule: Results are presented with provenance, exact first

    Scenario: Groups are labelled and ordered
      Given a query producing both exact and semantic results
      When the response is rendered
      Then exact matches SHALL appear first under a label identifying them as exact
      And semantic matches SHALL appear after, labelled as approximate

    Scenario: Semantic results name their source
      When a semantically retrieved passage is presented
      Then it SHALL name the document it came from
      And it SHALL be openable at the document platform

    Scenario: No combined score
      When a response containing both kinds of result is inspected
      Then no ordering value SHALL rank a semantic result against an exact one

    Scenario: A semantic hit is not an asset record
      Given a semantic result mentioning an asset by name
      When the response is presented
      Then it SHALL NOT be presented as that asset's specification or location
      And the asset's own record SHALL be reachable only through the exact results

  Rule: The asking person's authority is forwarded

    Scenario: Two people get different results
      Given two people with access to different workspaces
      When each runs the same natural-language query
      Then each SHALL receive only passages from workspaces they may read

    Scenario: Service credential is never end-user authority
      When a delegated query is made on behalf of a person
      Then the credential presented to the retrieval service SHALL be that person's
      And no query SHALL be made under a service credential on a person's behalf

    Scenario: No forwardable credential means local only
      Given a caller with no forwardable credential
      When a natural-language query is run
      Then only local results SHALL be returned
      And the semantic portion SHALL be reported as unavailable for lack of authority

  Rule: No specification content is ingested into the document platform

    Scenario: Only the query is sent
      When a natural-language query is delegated
      Then the transmitted payload SHALL contain the query text and routing scope
      And it SHALL contain no specification or annotation content

    Scenario: No indexing path exists
      When the system's operations are enumerated
      Then none SHALL push repository content into a document platform workspace

  Rule: Local search survives the retrieval service being unavailable

    Scenario: Unreachable service degrades the response, not the search
      Given the retrieval service is unreachable
      When a natural-language query is run
      Then the local results SHALL be returned
      And the response SHALL state that semantic results were unavailable and why

    Scenario: Slow service does not hold the response
      Given a retrieval service that does not answer within the configured time budget
      When a query is run
      Then the response SHALL be returned within that budget plus the local search time
      And the semantic portion SHALL be reported as unavailable

    Scenario: Reason is distinguishable
      When semantic results are unavailable
      Then the reported reason SHALL distinguish at least unconfigured, unreachable, rejected and timed out

  Rule: Unanswered queries are recorded locally

    Scenario: A semantic hit does not hide an exact miss
      Given a query with no exact results but two semantic results
      When the search completes
      Then the query SHALL be recorded as a miss

    Scenario: Misses stay local
      When a miss is recorded
      Then no request carrying it SHALL be made to any remote service
