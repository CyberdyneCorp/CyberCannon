# Spec Delta

## Purpose

Signing in, signing out, and the case that decides whether people trust the tool —
a session expiring while someone is midway through writing feedback.

## ADDED Requirements

### Requirement: An unauthenticated visitor is offered sign-in, not an error

A person arriving without a valid session SHALL be shown a sign-in affordance and
SHALL NOT be shown an error, a blank screen, or any project or asset content.

#### Scenario: Arriving signed out
- **WHEN** an unauthenticated person opens any address
- **THEN** they SHALL be offered sign-in
- **AND** no project or asset content SHALL be shown

### Requirement: Sign-in returns the person to where they were going

After signing in, the person SHALL be taken to the address they originally
requested, not to a default landing screen.

#### Scenario: Deep link through sign-in
- **GIVEN** an unauthenticated person opens a link to a specific asset
- **WHEN** they complete sign-in
- **THEN** they SHALL arrive at that asset

### Requirement: Expiry mid-edit never destroys unsaved work

When a session expires while a person has unsaved input, the application SHALL
preserve that input, offer to re-establish the session in place, and on success
SHALL allow the original action to be completed without the person retyping
anything.

#### Scenario: Session expires while writing an annotation
- **GIVEN** a person has typed an annotation and not yet submitted it
- **WHEN** their session expires and they submit
- **THEN** the text SHALL be preserved
- **AND** they SHALL be offered to re-authenticate in place
- **AND** on success the annotation SHALL be submitted with that text

#### Scenario: Re-authentication is declined
- **GIVEN** unsaved input and an expired session
- **WHEN** the person declines to re-authenticate
- **THEN** the input SHALL remain on screen and recoverable
- **AND** it SHALL NOT be submitted

### Requirement: Signing out clears local state

Signing out SHALL clear cached project and asset content held by the application,
so that a subsequent person using the same browser sees nothing of the previous
session.

#### Scenario: No content survives sign-out
- **GIVEN** a person has browsed several assets
- **WHEN** they sign out
- **THEN** no project or asset content SHALL remain reachable without signing in again

### Requirement: The identity in use is always visible

The application SHALL show which person the current session belongs to, so that
attribution of anything they write is never a surprise.

#### Scenario: Acting identity shown
- **WHEN** any authenticated screen is shown
- **THEN** the person the session belongs to SHALL be identified

### Requirement: An unmapped person is told before they are refused

When the signed-in person has no mapped git identity, the application SHALL state
this and SHALL indicate which actions are unavailable as a result, before they
attempt one — rather than only reporting a refusal after they have written
something.

#### Scenario: Unmapped person is warned early
- **GIVEN** a signed-in person with no mapped git identity
- **WHEN** they open an asset
- **THEN** the application SHALL state that actions writing to the repository are
  unavailable and why

### Requirement: An identity provider outage degrades rather than blanks

When the identity provider is unreachable but the person's session remains valid,
the application SHALL continue to serve reads and SHALL state that actions
requiring re-verification are temporarily unavailable.

#### Scenario: Reads continue during an outage
- **GIVEN** a valid session and an unreachable identity provider
- **WHEN** the person browses assets
- **THEN** browsing SHALL continue to work
- **AND** the unavailability SHALL be stated
