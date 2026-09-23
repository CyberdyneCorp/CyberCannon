# Generated from openspec/changes/fix-web-unknown-git-identity/specs/web-session/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:fix-web-unknown-git-identity @capability:web-session @spec:openspec/changes/fix-web-unknown-git-identity/specs/web-session/spec.md
Feature: web-session

  Rule: An unknown git mapping is not reported as an unmapped one

    Scenario: A credential silent about git identity raises no warning
      Given a signed-in person whose credential carries no git identity claim
      When they open any screen
      Then the application SHALL NOT state that they have no mapped git identity

    Scenario: A credential stating no git identity still raises the warning
      Given a signed-in person whose credential carries an empty git identity claim
      When they open any screen
      Then the application SHALL state that actions writing to the repository are unavailable and why
