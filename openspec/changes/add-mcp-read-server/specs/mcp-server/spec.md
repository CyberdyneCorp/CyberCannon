# Spec Delta

## Purpose

The Model Context Protocol surface through which an agent on a person's own
machine reads a project's canon — a local, read-only, process-spawned server that
returns prose an agent can act on rather than data it must parse.

## ADDED Requirements

### Requirement: Local process transport

The MCP server SHALL communicate over standard input and output as a process
spawned by its client. It SHALL NOT open a listening network port, and SHALL NOT
require a network connection in order to serve any read tool.

#### Scenario: Server runs with no network
- **GIVEN** a machine with no network connectivity
- **WHEN** an agent spawns the server and calls a read tool
- **THEN** the call SHALL succeed from local files

#### Scenario: No listening port
- **WHEN** the server is running
- **THEN** it SHALL NOT be reachable from any network socket

### Requirement: One server, both audiences

The same server SHALL serve a programmer's coding agent and an artist's authoring
tool without behavioural difference or separate builds. Any difference in what a
caller receives SHALL come from its identity or its requested lens, never from
which client connected.

#### Scenario: Identical results across clients
- **GIVEN** two different MCP clients configured with the same credential and lens
- **WHEN** both request the same asset's specification
- **THEN** both SHALL receive identical content

### Requirement: Read-only tool surface

The server SHALL expose only tools that read project state, plus maintenance of
its own derived index, plus — once a later change introduces them — the explicitly
enumerated proposal-shaped write tools of the `mcp-write-surface` capability and
nothing else. In this change no write tool exists. No tool SHALL modify a
specification file, an annotation, or any other repository content except through
that enumerated set.

#### Scenario: No mutating tool is advertised
- **WHEN** a client lists the server's available tools
- **THEN** no advertised tool SHALL modify repository content

#### Scenario: Repository is unchanged by reads
- **GIVEN** a clean repository working tree
- **WHEN** an agent calls every available read tool
- **THEN** the repository working tree SHALL remain clean

### Requirement: Promotion is prohibited, not deferred

The server SHALL NOT expose a tool that promotes an annotation into a durable rule
or constraint, in this or any future version, regardless of the roles held by the
actor the caller acts as. Promotion SHALL remain a human action on a human-facing
surface.

#### Scenario: Art director's agent cannot promote
- **GIVEN** a caller acting as an actor holding the art director role
- **WHEN** it attempts to promote an annotation to a rule
- **THEN** no such tool SHALL exist
- **AND** the request SHALL be refused

### Requirement: Responses are prose

Tool responses SHALL be formatted for direct consumption in a language model's
context window — readable text or markdown that a person could also read — rather
than raw structured data requiring further parsing. A tool MAY additionally offer
a structured form where a caller explicitly needs one.

#### Scenario: Specification returned as readable markdown
- **WHEN** an agent requests an asset's specification
- **THEN** the response SHALL be the markdown briefing a person would read

#### Scenario: Listings are compact
- **WHEN** an agent lists assets
- **THEN** the response SHALL be a compact table rather than a full record dump

### Requirement: Validation reuses the single implementation

The server's validation tool SHALL invoke the same validation behaviour as the
command-line tool, producing identical violations for identical inputs. The
server SHALL NOT contain its own copy of any validation rule.

#### Scenario: Agent and command line agree
- **GIVEN** an export that fails its triangle budget
- **WHEN** it is validated through the server and through the command line
- **THEN** both SHALL report the same violations with the same severities

### Requirement: Failures are legible to an agent

When a tool cannot answer — an unknown asset, a missing file, an unparseable
specification, a stale index — the server SHALL return an explanation naming the
cause and, where one exists, the action that would resolve it. It SHALL NOT return
an empty success, and SHALL NOT terminate the session on a recoverable error.

#### Scenario: Unknown asset identifier
- **WHEN** a tool is called with an asset identifier that does not exist
- **THEN** the response SHALL say so and SHALL offer the closest matching
  identifiers
- **AND** the session SHALL remain usable

#### Scenario: Unparseable specification does not kill the server
- **GIVEN** one specification file in the project is malformed
- **WHEN** an agent lists assets
- **THEN** the listing SHALL return the readable assets
- **AND** SHALL report the malformed file separately

### Requirement: Server is launchable from the command line

The system SHALL provide a command that starts the MCP server for a given project
directory, suitable for use as the launch command in an agent client's
configuration, and requiring no credential in order to serve reads.

#### Scenario: Launch without credentials
- **GIVEN** no identity is configured on the machine
- **WHEN** the server is launched and a read tool is called
- **THEN** the call SHALL succeed
