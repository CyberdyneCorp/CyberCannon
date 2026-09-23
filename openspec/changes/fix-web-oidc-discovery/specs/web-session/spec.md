# Spec Delta

## Purpose

Signing in against the identity service that actually exists: its endpoints
are read, not guessed; it is reached from the application's own origin; a
session outlives its first access token; signing out ends the identity
service's session as well as this tab's.

## ADDED Requirements

### Requirement: Sign-in endpoints are read from the issuer's discovery document

The application SHALL obtain the identity service's authorization, token and
end-session endpoints from the discovery document the configured issuer
publishes. It SHALL refuse a document whose issuer is not the configured one,
and SHALL NOT build any of these endpoints from a fixed path. When the
discovery document cannot be read, sign-in SHALL be reported as unavailable,
and every screen SHALL continue to be served.

#### Scenario: Endpoints come from discovery, not from fixed paths
- **GIVEN** an issuer whose discovery document names endpoints at non-default paths
- **WHEN** a person starts signing in
- **THEN** they SHALL be sent to the authorization endpoint the document names

#### Scenario: A discovery document for another issuer is refused
- **GIVEN** a discovery document whose issuer differs from the configured issuer
- **WHEN** it is read
- **THEN** none of its endpoints SHALL be used

#### Scenario: Unreadable discovery reports sign-in unavailable
- **GIVEN** an issuer whose discovery document cannot be read
- **WHEN** a person starts signing in
- **THEN** they SHALL be told sign-in is unavailable
- **AND** SHALL NOT be shown a crash

### Requirement: The browser never calls the identity service cross-origin

The application SHALL NOT depend on the identity service allowing cross-origin
requests from the application's origin. The browser SHALL send the token
exchange and renewal to the application's own origin, which SHALL forward them
to the discovered token endpoint as a public client: it SHALL add no client
secret, forward only the authorization-code and refresh-token grants, and keep
nothing.

#### Scenario: Token exchange goes through the application's own origin
- **GIVEN** an identity service that refuses cross-origin requests
- **WHEN** a person completes sign-in
- **THEN** the code exchange SHALL be sent to the application's own origin
- **AND** it SHALL be forwarded to the discovered token endpoint with no client secret

### Requirement: A session is renewed before its access token lapses

The application SHALL request a refresh token. While the tab is open, it SHALL
use that token to renew the session shortly before the access token lapses,
and SHALL replace the whole credential with the one returned, rotated refresh
token included. The refresh token SHALL be held only in the tab's session
storage and SHALL be removed on sign-out. It is issued by the identity service
to the person's browser and is not a credential the surface issues or holds.
When a renewal is refused, the session SHALL become expired and the in-place
re-authentication SHALL apply.

#### Scenario: A session outlives its first access token
- **GIVEN** a signed-in person whose access token is about to lapse
- **WHEN** the session is renewed
- **THEN** a new access token SHALL be in use without the person being asked anything
- **AND** the rotated refresh token SHALL replace the spent one

#### Scenario: A refused renewal falls back to in-place re-authentication
- **GIVEN** a signed-in person whose refresh token is refused
- **WHEN** the session is renewed
- **THEN** the session SHALL be expired, keeping who it belonged to

### Requirement: Signing out ends the identity service's session

Signing out SHALL end the person's session at the identity service as well as
clearing local state, so that the next person to sign in on the same browser is
asked who they are instead of being signed in as the previous person.

#### Scenario: The next person on a shared browser is asked to sign in
- **GIVEN** a person signed in on a shared browser
- **WHEN** they sign out and somebody else starts signing in
- **THEN** the identity service SHALL ask who is signing in

### Requirement: The acting identity is named from the identity token

The application SHALL name the acting person from the identity token's name or
email when the access token carries neither. It SHALL present only the access
token to the surface, and never an identity token.

#### Scenario: A person is named, not shown as a subject identifier
- **GIVEN** an access token that carries a subject but no name or email
- **AND** an identity token that carries the person's email
- **WHEN** any authenticated screen is shown
- **THEN** the person SHALL be identified by that email

#### Scenario: An identity token is never the surface credential
- **GIVEN** a token response that carries an identity token and no access token
- **WHEN** sign-in completes
- **THEN** nobody SHALL be signed in
