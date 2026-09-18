# Spec Delta

## Purpose

Establishes how a networked caller becomes a person the domain can reason about —
which credential flows are accepted, what makes a credential trustworthy, that
identity and tenancy come only from verified claims, and that translating claims
is the adapter's whole job while deciding what may happen stays domain policy.

## ADDED Requirements

### Requirement: Identity and tenant come only from verified claims

The acting person and the project tenancy a request operates within SHALL be
derived exclusively from claims in a verified credential. The surface SHALL NOT
accept an actor identifier, tenant identifier, organisation, role or group taken
from a path segment, a query parameter, a request body or a request header other
than the credential itself, and SHALL ignore any such value if supplied.

#### Scenario: Body-supplied identity is ignored
- **GIVEN** a request whose credential verifies to one person
- **WHEN** the request body names a different person as the actor
- **THEN** the request SHALL be evaluated as the credential's person
- **AND** the supplied value SHALL have no effect

#### Scenario: Path-supplied tenant cannot widen access
- **GIVEN** a credential whose claims grant access to one tenant
- **WHEN** a request addresses a project belonging to another tenant
- **THEN** the request SHALL be refused

### Requirement: Credentials are verified against the issuer's published keys

A credential SHALL be accepted only when its signature verifies against a key
published by the configured issuer, its issuer and audience match the configured
values, and it is within its validity period. A credential failing any of these
SHALL be refused as unauthenticated, and the reason SHALL be recorded without
being disclosed in a way that distinguishes between a wrong signature and a wrong
audience to the caller.

#### Scenario: Expired credential is refused
- **WHEN** a request presents a credential past its validity period
- **THEN** it SHALL be refused as unauthenticated

#### Scenario: Wrong audience is refused
- **WHEN** a request presents a credential issued for a different audience
- **THEN** it SHALL be refused as unauthenticated

#### Scenario: Unverifiable signature is refused
- **WHEN** a request presents a credential whose signature does not verify against
  any published key of the configured issuer
- **THEN** it SHALL be refused as unauthenticated

#### Scenario: Key rotation is tolerated without a restart
- **GIVEN** the issuer publishes a new signing key
- **WHEN** a credential signed by that key is presented
- **THEN** it SHALL be accepted without the service being restarted or
  reconfigured

### Requirement: The credential's representation never reaches the core

Authorization decisions and recorded actions SHALL be expressed in terms of a
resolved actor carrying a stable identifier and a set of domain roles. Claim
names, group names, token encoding, issuer identity and the identity service's
data model SHALL NOT be visible beyond the adapter that performs verification, so
that authorization behaviour can be exercised with no identity service present.

#### Scenario: Authorization tested without an identity service
- **GIVEN** no identity service is configured or reachable
- **WHEN** an authorization decision is evaluated for a constructed actor
- **THEN** the decision SHALL be produced from that actor's identifier and roles
  alone

#### Scenario: No claim vocabulary in recorded actions
- **WHEN** an action is recorded
- **THEN** the record SHALL identify the actor by its stable identifier
- **AND** SHALL NOT contain claim or group names from the identity service

### Requirement: Group-to-role mapping is configuration, and unmapped grants nothing

The translation from the identity service's groups and claims to domain roles
SHALL be driven by configuration rather than by code that names specific groups. A
group with no configured mapping SHALL grant no role, and a credential carrying
only unmapped groups SHALL resolve to an actor with no roles rather than be
refused.

#### Scenario: Unmapped group grants nothing
- **GIVEN** a credential carrying a group with no configured mapping
- **WHEN** the actor is resolved
- **THEN** the actor SHALL hold no role from that group

#### Scenario: A role-less actor is resolved, not rejected
- **GIVEN** a credential whose groups all lack mappings
- **WHEN** a request is made
- **THEN** the actor SHALL be resolved with no roles
- **AND** role-requiring operations SHALL be refused naming the required role

#### Scenario: Adding a mapping requires no code change
- **GIVEN** a new group in the identity service
- **WHEN** it is mapped to a domain role in configuration
- **THEN** credentials carrying that group SHALL resolve with that role

### Requirement: Authorization is decided by domain policy, never by the adapter

Whether a resolved actor may perform an operation SHALL be decided by domain
policy evaluated over the actor's roles and the subject of the operation. The
verification adapter SHALL NOT permit, deny or shortcut any operation, and there
SHALL be no permission that exists only in the adapter.

#### Scenario: Identical decision for identical actors
- **GIVEN** two actors with the same roles, one resolved from a verified
  credential and one constructed directly
- **WHEN** the same operation is evaluated for each
- **THEN** both SHALL receive the same decision

#### Scenario: The adapter cannot grant
- **WHEN** the verification adapter resolves an actor
- **THEN** the resolution SHALL produce an identifier and roles only
- **AND** SHALL NOT produce an allow or deny outcome for any operation

### Requirement: Interactive sign-in uses authorization code with proof of possession

A person signing in through a browser-based application SHALL do so by an
authorization-code exchange bound to a proof key generated by that application.
The surface SHALL NOT accept a password, SHALL NOT issue or hold a long-lived
credential on the person's behalf, and no confidential client secret SHALL be
required by or embedded in a browser-delivered application.

#### Scenario: Authorization code without proof is refused
- **WHEN** an authorization code is exchanged without the matching proof
- **THEN** the exchange SHALL fail and no credential SHALL be issued

#### Scenario: The surface never sees a password
- **WHEN** a person signs in
- **THEN** the credential presented to the surface SHALL be an issuer-signed token
- **AND** no password SHALL be transmitted to or stored by the surface

### Requirement: The command line signs in by device authorization and stores credentials in the operating system keychain

A person authenticating from a terminal SHALL be able to complete sign-in by
approving a device authorization in a browser, without pasting a credential. The
resulting credential SHALL be stored in the operating system's credential store,
SHALL NOT be written into the repository or any file inside it, and SHALL be
removable by an explicit sign-out.

#### Scenario: Credential is not written into the repository
- **GIVEN** a person completes a terminal sign-in inside a repository working copy
- **WHEN** the working tree is inspected
- **THEN** it SHALL be unchanged
- **AND** no credential SHALL exist in any file under the repository

#### Scenario: Sign-out removes the credential
- **GIVEN** a stored credential
- **WHEN** the person signs out
- **THEN** the credential SHALL be removed from the credential store

#### Scenario: Validation still requires no sign-in
- **GIVEN** no credential has ever been stored on a machine
- **WHEN** an export is validated locally
- **THEN** validation SHALL complete normally

### Requirement: Background work authenticates as the system and is attributed as automation

Work performed with no live human caller SHALL authenticate with a service
credential, SHALL resolve to an actor identified as automation, SHALL be recorded
as automation rather than as any person, and SHALL be refused every operation the
project reserves to a person.

#### Scenario: Scheduled refresh names no person
- **WHEN** a scheduled refresh performs a recorded action
- **THEN** the record SHALL identify it as automation
- **AND** SHALL NOT name any person as responsible

#### Scenario: Service credential cannot impersonate
- **GIVEN** a service credential
- **WHEN** a request using it supplies a person's identifier
- **THEN** the request SHALL be evaluated as automation
- **AND** the supplied identifier SHALL have no effect

### Requirement: Identity outage degrades within a bounded window

When the identity service is unreachable, the surface SHALL continue to verify
credentials against the most recently retrieved published keys for a bounded
configured period, and SHALL continue to serve requests whose credentials still
verify and remain within their validity period. Beyond that period, or for a
credential requiring a fresh exchange, requests SHALL be refused with a message
naming the identity service as unavailable, and SHALL NOT be served as an
anonymous or elevated actor.

#### Scenario: Reads survive a short identity outage
- **GIVEN** published keys retrieved before the identity service became unreachable
- **WHEN** a caller presents a valid, unexpired credential signed by one of them
- **THEN** the request SHALL be served

#### Scenario: Degradation never elevates
- **GIVEN** the identity service is unreachable
- **WHEN** a request presents no credential
- **THEN** it SHALL be refused
- **AND** SHALL NOT be served as an anonymous or default actor

#### Scenario: Beyond the window, refusal names the cause
- **GIVEN** the identity service has been unreachable longer than the configured
  period
- **WHEN** any authenticated request is made
- **THEN** it SHALL be refused with a message naming the identity service as
  unavailable
