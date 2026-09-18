# Generated from openspec/changes/add-web-app-shell/specs/web-session/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-app-shell @capability:web-session @spec:openspec/changes/add-web-app-shell/specs/web-session/spec.md
Feature: web-session

  Rule: An unauthenticated visitor is offered sign-in, not an error

    Scenario: Arriving signed out
      When an unauthenticated person opens any address
      Then they SHALL be offered sign-in
      And no project or asset content SHALL be shown

  Rule: Sign-in returns the person to where they were going

    Scenario: Deep link through sign-in
      Given an unauthenticated person opens a link to a specific asset
      When they complete sign-in
      Then they SHALL arrive at that asset

  Rule: Expiry mid-edit never destroys unsaved work

    Scenario: Session expires while writing an annotation
      Given a person has typed an annotation and not yet submitted it
      When their session expires and they submit
      Then the text SHALL be preserved
      And they SHALL be offered to re-authenticate in place
      And on success the annotation SHALL be submitted with that text

    Scenario: Re-authentication is declined
      Given unsaved input and an expired session
      When the person declines to re-authenticate
      Then the input SHALL remain on screen and recoverable
      And it SHALL NOT be submitted

  Rule: Signing out clears local state

    Scenario: No content survives sign-out
      Given a person has browsed several assets
      When they sign out
      Then no project or asset content SHALL remain reachable without signing in again

  Rule: The identity in use is always visible

    Scenario: Acting identity shown
      When any authenticated screen is shown
      Then the person the session belongs to SHALL be identified

  Rule: An unmapped person is told before they are refused

    Scenario: Unmapped person is warned early
      Given a signed-in person with no mapped git identity
      When they open an asset
      Then the application SHALL state that actions writing to the repository are unavailable and why

  Rule: An identity provider outage degrades rather than blanks

    Scenario: Reads continue during an outage
      Given a valid session and an unreachable identity provider
      When the person browses assets
      Then browsing SHALL continue to work
      And the unavailability SHALL be stated
