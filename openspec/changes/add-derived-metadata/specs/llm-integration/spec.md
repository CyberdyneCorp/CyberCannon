# Spec Delta

## Purpose

Defines the single way CyberCanon reaches a language or vision model — an
OpenAI-compatible endpoint selected entirely by environment — and guarantees that
every feature built on it disappears cleanly when no model is available.

## ADDED Requirements

### Requirement: One wire protocol

The system SHALL communicate with language and vision models exclusively through
the OpenAI-compatible Chat Completions interface. It SHALL NOT implement a second
provider protocol, and SHALL NOT depend on features absent from that interface,
so that any compatible endpoint — a commercial service, a self-hosted gateway, or
a local proxy — can serve it without code changes.

#### Scenario: Endpoint substituted without code change
- **GIVEN** a deployment configured against one compatible endpoint
- **WHEN** it is reconfigured to a different compatible endpoint
- **THEN** all model-backed features SHALL continue to work with no change to the
  built artifact

#### Scenario: No vendor-specific feature is required
- **GIVEN** a compatible endpoint implementing only chat completions
- **WHEN** any model-backed feature runs
- **THEN** it SHALL succeed without requiring provider extensions

### Requirement: Configuration comes from the environment

Model access SHALL be configured by environment variables covering: a master
enable switch, the endpoint base URL, the credential, a text model identifier, a
vision model identifier, a request timeout and a retry budget. The enable switch
SHALL default to disabled. No model configuration SHALL be compiled into the
build or required in a specification file.

#### Scenario: Disabled by default
- **GIVEN** no model configuration in the environment
- **WHEN** the system starts
- **THEN** model-backed features SHALL report themselves unavailable
- **AND** every other feature SHALL work normally

#### Scenario: Enabled by configuration alone
- **GIVEN** the enable switch, endpoint, credential and model identifiers are set
- **WHEN** a model-backed feature is invoked
- **THEN** it SHALL call the configured endpoint

### Requirement: Model identifiers are opaque

A configured model identifier SHALL be passed to the endpoint verbatim. The system
SHALL NOT validate it against a list of known models, SHALL NOT alter behaviour
based on its value, and SHALL NOT refuse an unrecognised identifier.

#### Scenario: Unrecognised model accepted
- **GIVEN** a model identifier the system has never seen
- **WHEN** a model-backed feature is invoked
- **THEN** the identifier SHALL be sent unchanged to the endpoint

#### Scenario: No behavioural branching on model name
- **GIVEN** two different configured model identifiers
- **WHEN** the same feature is invoked under each
- **THEN** the request the system constructs SHALL differ only in the model
  identifier

### Requirement: Provider details never leave the adapter

Use cases and domain logic SHALL interact with models only through an abstract
capability — given this input, return this text — and SHALL NOT observe the
endpoint, the credential, the model identifier, request or response structures, or
any provider-specific error. Model-backed features SHALL be testable with no
endpoint reachable.

#### Scenario: Features tested without an endpoint
- **GIVEN** no configured endpoint and no network
- **WHEN** a model-backed use case is exercised against a substitute
- **THEN** it SHALL run to completion and produce its result

### Requirement: Every failure degrades identically

Disabled configuration, missing configuration, an unreachable endpoint, an
authentication failure, a timeout, a rate limit and a malformed response SHALL all
result in the same observable outcome: the model-backed feature is unavailable,
the cause is reported, and no other behaviour of the system changes.

#### Scenario: Timeout does not fail the surrounding operation
- **GIVEN** an endpoint that does not respond within the configured timeout
- **WHEN** a feature requests generation as part of a larger operation
- **THEN** the larger operation SHALL complete
- **AND** the generated content SHALL be reported as unavailable

#### Scenario: Cause is reported
- **WHEN** generation is unavailable
- **THEN** the system SHALL state the reason distinguishing at least disabled,
  misconfigured, unreachable and rejected

### Requirement: Core paths never depend on a model

Specification validation, specification compilation, asset lookup and search SHALL
produce identical results whether model access is configured or not, and SHALL
never block on a model call.

#### Scenario: Validation unaffected by model availability
- **GIVEN** an export and its specification
- **WHEN** it is validated with model access enabled and again with it disabled
- **THEN** the reports SHALL be identical

#### Scenario: Compiled specification unaffected
- **WHEN** a specification is compiled with model access enabled and again disabled
- **THEN** the two outputs SHALL be byte-identical

### Requirement: Bounded and non-retrying-forever requests

Every model request SHALL be bounded by the configured timeout and SHALL retry at
most the configured number of times before reporting unavailability. The system
SHALL NOT retry a request rejected for authentication or for an invalid request.

#### Scenario: Retry budget respected
- **GIVEN** a retry budget of two and an endpoint failing transiently
- **WHEN** generation is requested
- **THEN** at most three attempts SHALL be made in total

#### Scenario: Authentication failure is not retried
- **WHEN** the endpoint rejects the credential
- **THEN** exactly one attempt SHALL be made
- **AND** the cause SHALL be reported as rejected

### Requirement: Content sent to a model is recorded in scope

The system SHALL define and document which project content each model-backed
feature transmits, and SHALL transmit nothing beyond that scope. Specifications,
annotations and exports SHALL NOT be transmitted by a feature whose declared scope
is a single image.

#### Scenario: Image description sends only the image
- **WHEN** a concept view is described
- **THEN** only that image and a fixed instruction SHALL be transmitted
- **AND** no specification content SHALL be included
