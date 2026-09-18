# Generated from openspec/changes/add-derived-metadata/specs/llm-integration/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-derived-metadata @capability:llm-integration @spec:openspec/changes/add-derived-metadata/specs/llm-integration/spec.md
Feature: llm-integration

  Rule: One wire protocol

    Scenario: Endpoint substituted without code change
      Given a deployment configured against one compatible endpoint
      When it is reconfigured to a different compatible endpoint
      Then all model-backed features SHALL continue to work with no change to the built artifact

    Scenario: No vendor-specific feature is required
      Given a compatible endpoint implementing only chat completions
      When any model-backed feature runs
      Then it SHALL succeed without requiring provider extensions

  Rule: Configuration comes from the environment

    Scenario: Disabled by default
      Given no model configuration in the environment
      When the system starts
      Then model-backed features SHALL report themselves unavailable
      And every other feature SHALL work normally

    Scenario: Enabled by configuration alone
      Given the enable switch, endpoint, credential and model identifiers are set
      When a model-backed feature is invoked
      Then it SHALL call the configured endpoint

  Rule: Model identifiers are opaque

    Scenario: Unrecognised model accepted
      Given a model identifier the system has never seen
      When a model-backed feature is invoked
      Then the identifier SHALL be sent unchanged to the endpoint

    Scenario: No behavioural branching on model name
      Given two different configured model identifiers
      When the same feature is invoked under each
      Then the request the system constructs SHALL differ only in the model identifier

  Rule: Provider details never leave the adapter

    Scenario: Features tested without an endpoint
      Given no configured endpoint and no network
      When a model-backed use case is exercised against a substitute
      Then it SHALL run to completion and produce its result

  Rule: Every failure degrades identically

    Scenario: Timeout does not fail the surrounding operation
      Given an endpoint that does not respond within the configured timeout
      When a feature requests generation as part of a larger operation
      Then the larger operation SHALL complete
      And the generated content SHALL be reported as unavailable

    Scenario: Cause is reported
      When generation is unavailable
      Then the system SHALL state the reason distinguishing at least disabled, misconfigured, unreachable and rejected

  Rule: Core paths never depend on a model

    Scenario: Validation unaffected by model availability
      Given an export and its specification
      When it is validated with model access enabled and again with it disabled
      Then the reports SHALL be identical

    Scenario: Compiled specification unaffected
      When a specification is compiled with model access enabled and again disabled
      Then the two outputs SHALL be byte-identical

  Rule: Bounded and non-retrying-forever requests

    Scenario: Retry budget respected
      Given a retry budget of two and an endpoint failing transiently
      When generation is requested
      Then at most three attempts SHALL be made in total

    Scenario: Authentication failure is not retried
      When the endpoint rejects the credential
      Then exactly one attempt SHALL be made
      And the cause SHALL be reported as rejected

  Rule: Content sent to a model is recorded in scope

    Scenario: Image description sends only the image
      When a concept view is described
      Then only that image and a fixed instruction SHALL be transmitted
      And no specification content SHALL be included
