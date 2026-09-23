# Generated from openspec/changes/fix-web-oidc-discovery/specs/web-session/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:fix-web-oidc-discovery @capability:web-session @spec:openspec/changes/fix-web-oidc-discovery/specs/web-session/spec.md
Feature: web-session

  Rule: Sign-in endpoints are read from the issuer's discovery document

    Scenario: Endpoints come from discovery, not from fixed paths
      Given an issuer whose discovery document names endpoints at non-default paths
      When a person starts signing in
      Then they SHALL be sent to the authorization endpoint the document names

    Scenario: A discovery document for another issuer is refused
      Given a discovery document whose issuer differs from the configured issuer
      When it is read
      Then none of its endpoints SHALL be used

    Scenario: A hung identity service is an outage, not a hang
      Given an identity service that accepts connections and never answers
      When a person starts signing in, or the session is renewed
      Then sign-in or renewal SHALL be reported unavailable within the timeout

    Scenario: Unreadable discovery reports sign-in unavailable
      Given an issuer whose discovery document cannot be read
      When a person starts signing in
      Then they SHALL be told sign-in is unavailable
      And SHALL NOT be shown a crash

  Rule: The browser never calls the identity service cross-origin

    Scenario: Token exchange goes through the application's own origin
      Given an identity service that refuses cross-origin requests
      When a person completes sign-in
      Then the code exchange SHALL be sent to the application's own origin
      And it SHALL be forwarded to the discovered token endpoint with no client secret

  Rule: A session is renewed before its access token lapses

    Scenario: A session outlives its first access token
      Given a signed-in person whose access token is about to lapse
      When the session is renewed
      Then a new access token SHALL be in use without the person being asked anything
      And the rotated refresh token SHALL replace the spent one

    Scenario: An access token refused before its renewal fired is renewed silently
      Given a signed-in person with a refresh token whose access token the surface refuses
      When they submit a write
      Then the session SHALL be renewed and the write re-sent under its key
      And no re-authentication SHALL be offered

    Scenario: A renewal the identity service did not answer is retried
      Given a renewal that the identity service did not answer
      When the retry delay passes
      Then the renewal SHALL be attempted again with the same refresh token

    Scenario: A duplicated tab does not spend a rotated refresh token
      Given two tabs of the application holding the same refresh token
      When both are due to renew
      Then the refresh token SHALL be spent once
      And both tabs SHALL hold the renewed credential

    Scenario: A refused renewal falls back to in-place re-authentication
      Given a signed-in person whose refresh token is refused
      When the session is renewed
      Then the session SHALL be expired, keeping who it belonged to

  Rule: Signing out ends the identity service's session

    Scenario: The next person on a shared browser is asked to sign in
      Given a person signed in on a shared browser
      When they sign out and somebody else starts signing in
      Then the identity service SHALL ask who is signing in

  Rule: The acting identity is named from the identity token

    Scenario: A person is named, not shown as a subject identifier
      Given an access token that carries a subject but no name or email
      And an identity token that carries the person's email
      When any authenticated screen is shown
      Then the person SHALL be identified by that email

    Scenario: An identity token is never the surface credential
      Given a token response that carries an identity token and no access token
      When sign-in completes
      Then nobody SHALL be signed in
