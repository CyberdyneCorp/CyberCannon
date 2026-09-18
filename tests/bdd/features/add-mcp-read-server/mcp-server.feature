# Generated from openspec/changes/add-mcp-read-server/specs/mcp-server/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-mcp-read-server @capability:mcp-server @spec:openspec/changes/add-mcp-read-server/specs/mcp-server/spec.md
Feature: mcp-server

  Rule: Local process transport

    Scenario: Server runs with no network
      Given a machine with no network connectivity
      When an agent spawns the server and calls a read tool
      Then the call SHALL succeed from local files

    Scenario: No listening port
      When the server is running
      Then it SHALL NOT be reachable from any network socket

  Rule: One server, both audiences

    Scenario: Identical results across clients
      Given two different MCP clients configured with the same credential and lens
      When both request the same asset's specification
      Then both SHALL receive identical content

  Rule: Read-only tool surface

    Scenario: No mutating tool is advertised
      When a client lists the server's available tools
      Then no advertised tool SHALL modify repository content

    Scenario: Repository is unchanged by reads
      Given a clean repository working tree
      When an agent calls every available read tool
      Then the repository working tree SHALL remain clean

  Rule: Promotion is prohibited, not deferred

    Scenario: Art director's agent cannot promote
      Given a caller acting as an actor holding the art director role
      When it attempts to promote an annotation to a rule
      Then no such tool SHALL exist
      And the request SHALL be refused

  Rule: Responses are prose

    Scenario: Specification returned as readable markdown
      When an agent requests an asset's specification
      Then the response SHALL be the markdown briefing a person would read

    Scenario: Listings are compact
      When an agent lists assets
      Then the response SHALL be a compact table rather than a full record dump

  Rule: Validation reuses the single implementation

    Scenario: Agent and command line agree
      Given an export that fails its triangle budget
      When it is validated through the server and through the command line
      Then both SHALL report the same violations with the same severities

  Rule: Failures are legible to an agent

    Scenario: Unknown asset identifier
      When a tool is called with an asset identifier that does not exist
      Then the response SHALL say so and SHALL offer the closest matching identifiers
      And the session SHALL remain usable

    Scenario: Unparseable specification does not kill the server
      Given one specification file in the project is malformed
      When an agent lists assets
      Then the listing SHALL return the readable assets
      And SHALL report the malformed file separately

  Rule: Server is launchable from the command line

    Scenario: Launch without credentials
      Given no identity is configured on the machine
      When the server is launched and a read tool is called
      Then the call SHALL succeed
