# Generated from openspec/changes/add-web-backend/specs/auth-integration/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-backend @capability:auth-integration @spec:openspec/changes/add-web-backend/specs/auth-integration/spec.md
Feature: auth-integration

  Rule: Identity and tenant come only from verified claims

    Scenario: Body-supplied identity is ignored
      Given a request whose credential verifies to one person
      When the request body names a different person as the actor
      Then the request SHALL be evaluated as the credential's person
      And the supplied value SHALL have no effect

    Scenario: Path-supplied tenant cannot widen access
      Given a credential whose claims grant access to one tenant
      When a request addresses a project belonging to another tenant
      Then the request SHALL be refused

  Rule: Credentials are verified against the issuer's published keys

    Scenario: Expired credential is refused
      When a request presents a credential past its validity period
      Then it SHALL be refused as unauthenticated

    Scenario: Wrong audience is refused
      When a request presents a credential issued for a different audience
      Then it SHALL be refused as unauthenticated

    Scenario: Unverifiable signature is refused
      When a request presents a credential whose signature does not verify against any published key of the configured issuer
      Then it SHALL be refused as unauthenticated

    Scenario: Key rotation is tolerated without a restart
      Given the issuer publishes a new signing key
      When a credential signed by that key is presented
      Then it SHALL be accepted without the service being restarted or reconfigured

  Rule: The credential's representation never reaches the core

    Scenario: Authorization tested without an identity service
      Given no identity service is configured or reachable
      When an authorization decision is evaluated for a constructed actor
      Then the decision SHALL be produced from that actor's identifier and roles alone

    Scenario: No claim vocabulary in recorded actions
      When an action is recorded
      Then the record SHALL identify the actor by its stable identifier
      And SHALL NOT contain claim or group names from the identity service

  Rule: Group-to-role mapping is configuration, and unmapped grants nothing

    Scenario: Unmapped group grants nothing
      Given a credential carrying a group with no configured mapping
      When the actor is resolved
      Then the actor SHALL hold no role from that group

    Scenario: A role-less actor is resolved, not rejected
      Given a credential whose groups all lack mappings
      When a request is made
      Then the actor SHALL be resolved with no roles
      And role-requiring operations SHALL be refused naming the required role

    Scenario: Adding a mapping requires no code change
      Given a new group in the identity service
      When it is mapped to a domain role in configuration
      Then credentials carrying that group SHALL resolve with that role

  Rule: Authorization is decided by domain policy, never by the adapter

    Scenario: Identical decision for identical actors
      Given two actors with the same roles, one resolved from a verified credential and one constructed directly
      When the same operation is evaluated for each
      Then both SHALL receive the same decision

    Scenario: The adapter cannot grant
      When the verification adapter resolves an actor
      Then the resolution SHALL produce an identifier and roles only
      And SHALL NOT produce an allow or deny outcome for any operation

  Rule: Interactive sign-in uses authorization code with proof of possession

    Scenario: Authorization code without proof is refused
      When an authorization code is exchanged without the matching proof
      Then the exchange SHALL fail and no credential SHALL be issued

    Scenario: The surface never sees a password
      When a person signs in
      Then the credential presented to the surface SHALL be an issuer-signed token
      And no password SHALL be transmitted to or stored by the surface

  Rule: The command line signs in by device authorization and stores credentials in the operating system keychain

    Scenario: Credential is not written into the repository
      Given a person completes a terminal sign-in inside a repository working copy
      When the working tree is inspected
      Then it SHALL be unchanged
      And no credential SHALL exist in any file under the repository

    Scenario: Sign-out removes the credential
      Given a stored credential
      When the person signs out
      Then the credential SHALL be removed from the credential store

    Scenario: Validation still requires no sign-in
      Given no credential has ever been stored on a machine
      When an export is validated locally
      Then validation SHALL complete normally

  Rule: Background work authenticates as the system and is attributed as automation

    Scenario: Scheduled refresh names no person
      When a scheduled refresh performs a recorded action
      Then the record SHALL identify it as automation
      And SHALL NOT name any person as responsible

    Scenario: Service credential cannot impersonate
      Given a service credential
      When a request using it supplies a person's identifier
      Then the request SHALL be evaluated as automation
      And the supplied identifier SHALL have no effect

  Rule: Identity outage degrades within a bounded window

    Scenario: Reads survive a short identity outage
      Given published keys retrieved before the identity service became unreachable
      When a caller presents a valid, unexpired credential signed by one of them
      Then the request SHALL be served

    Scenario: Degradation never elevates
      Given the identity service is unreachable
      When a request presents no credential
      Then it SHALL be refused
      And SHALL NOT be served as an anonymous or default actor

    Scenario: Beyond the window, refusal names the cause
      Given the identity service has been unreachable longer than the configured period
      When any authenticated request is made
      Then it SHALL be refused with a message naming the identity service as unavailable
