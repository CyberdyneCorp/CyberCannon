# Generated from openspec/changes/add-mcp-read-server/specs/agent-identity/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-mcp-read-server @capability:agent-identity @spec:openspec/changes/add-mcp-read-server/specs/agent-identity/spec.md
Feature: agent-identity

  Rule: Identity comes from the credential, never from a parameter

    Scenario: Claimed role is ignored
      Given a caller whose credential resolves to an actor holding the artist role
      When it supplies a parameter claiming the art director role
      Then the system SHALL evaluate the request as the artist
      And the supplied claim SHALL have no effect

    Scenario: Claimed identity is ignored
      When a caller supplies an actor identifier differing from its credential
      Then the system SHALL use the credential's actor

  Rule: An agent acts as a person and never escalates

    Scenario: Agent denied what its person is denied
      Given an actor who may not read a given project
      When an agent acting as that actor requests an asset from that project
      Then the request SHALL be refused

  Rule: The credential's format never reaches the core

    Scenario: Authorization verified without an identity service
      Given no identity service is reachable
      When an authorization decision is evaluated for a resolved actor
      Then the decision SHALL be produced from the actor's roles alone

  Rule: Reads degrade to a local actor when no identity is configured

    Scenario: Read works with no credential
      Given no credential is configured
      When an agent reads an asset's specification
      Then the read SHALL succeed

    Scenario: Role-requiring action refused with a reason
      Given no credential is configured
      When an action requiring a role is attempted
      Then it SHALL be refused with a message naming the required role

  Rule: Identity outage degrades rather than blocks

    Scenario: Reads survive an identity outage
      Given an actor resolved earlier and an identity service now unreachable
      When that caller reads an asset
      Then the read SHALL succeed

    Scenario: Cached actor expires
      Given a cached actor older than the permitted period
      When a role-requiring action is attempted
      Then it SHALL be refused as unverifiable

  Rule: Actions are attributed to the person and the agent

    Scenario: Attribution names both
      When an action is recorded for an agent acting as a given actor
      Then the record SHALL identify that actor as responsible
      And SHALL identify the agent as the instrument

    Scenario: Unattributable action is refused
      When an action would be recorded with no resolvable actor
      Then it SHALL be refused rather than recorded anonymously

  Rule: Agents never author constraints

    Scenario: Unattainable budget is reported, not changed
      Given an asset with a triangle budget an agent cannot meet
      When the agent reports that the budget is unattainable
      Then the report SHALL be recorded as an observation
      And the recorded triangle budget SHALL be unchanged

    Scenario: Constraint edit refused for every role
      When an automated caller attempts to modify a constraint while acting as an actor holding any role
      Then the attempt SHALL be refused

  Rule: Autonomous runs are attributed as automation

    Scenario: Scheduled run cannot act as a person
      Given a run with no human caller
      When it performs a recorded action
      Then the record SHALL identify it as automation
      And SHALL NOT name any person as responsible

  Rule: A project records the mapping between identity subjects and git authors

    Scenario: One entry binds both identities
      Given an entry binding the subject `auth|rafa` to the display name `Rafa`, the git emails `rafa@cyberdyne.com` and `rafa@personal.dev`, and the default role `ARTIST`
      When either that subject or either email is resolved to an actor
      Then the same actor SHALL be returned, carrying that display name and that default role

    Scenario: A project without a mapping still works
      Given a project that has no actor mapping
      When an asset's specification is read
      Then the read SHALL succeed
      And every git author encountered SHALL resolve as unmapped

  Rule: Git authors and actors resolve in both directions

    Scenario: Commit author is recognised as the person
      Given a mapping entry listing the email `rafa@cyberdyne.com`
      When a commit authored by `RAFA@Cyberdyne.com` is resolved
      Then it SHALL resolve to that entry's actor

    Scenario: Git identity for acting on a person's behalf
      Given an actor whose entry lists `rafa@cyberdyne.com` then `rafa@personal.dev`
      When the git author identity for that actor is requested
      Then it SHALL be that actor's display name with `rafa@cyberdyne.com`

    Scenario: Round trip is stable
      When an actor is resolved to a git author identity and that identity's email is resolved back to an actor
      Then the original actor SHALL be returned

  Rule: An unmapped git author resolves to an explicitly unknown actor

    Scenario: Unmapped author is preserved and flagged
      Given a commit authored by an email present in no mapping entry
      When its author is resolved
      Then an explicitly unknown actor SHALL be returned carrying that email
      And any response naming it SHALL mark it as unmapped

    Scenario: A near miss is never guessed
      Given a mapping entry listing `rafa@cyberdyne.com`
      When a commit authored by `r.santos@cyberdyne.com` is resolved
      Then the result SHALL be an unknown actor
      And SHALL NOT be the actor holding `rafa@cyberdyne.com`

    Scenario: Unmapped authors are enumerable
      Given a project whose history contains two authors absent from the mapping
      When the project's unmapped authors are requested
      Then both emails SHALL be listed

  Rule: The actor mapping is authored content and is validated structurally

    Scenario: Duplicate email is a violation
      Given two entries that both list `rafa@cyberdyne.com`
      When the mapping is validated
      Then a violation SHALL be reported naming that email and both entries

    Scenario: Duplicate subject is a violation
      Given two entries that declare the same identity subject
      When the mapping is validated
      Then a violation SHALL be reported naming that subject

    Scenario: Unknown role is a violation
      Given an entry whose default role is outside the defined role set
      When the mapping is validated
      Then a violation SHALL be reported naming the entry and the available roles

    Scenario: Mapping validation needs nothing external
      Given no identity service is reachable and the machine has no network
      When the mapping is validated
      Then validation SHALL complete and report its violations normally

  Rule: Provider claims take precedence over the mapping file

    Scenario: Provider-supplied emails win
      Given a provider that resolves an actor together with its git author emails
      When that actor's git author identity is requested
      Then the provider's emails SHALL be used
      And the mapping file SHALL NOT change the result

    Scenario: The file answers what the provider does not
      Given a provider that resolves an actor but supplies no git author emails
      When that actor's git author identity is requested
      Then the emails SHALL come from the mapping file entry for that subject

    Scenario: Disagreement is surfaced
      Given a provider and a mapping file that bind the same subject to different git author emails
      When that actor is resolved
      Then the provider's emails SHALL be used
      And the system SHALL report that the mapping file entry disagrees

  Rule: Attribution is presented through the resolved actor

    Scenario: A location answer names the person
      Given an asset whose art owner is recorded as `rafa@cyberdyne.com` and a mapping entry binding that email to the display name `Rafa`
      When the asset's location is requested
      Then the response SHALL name the art owner as `Rafa`

    Scenario: An unmapped owner is shown as unmapped
      Given an asset whose art owner is an email present in no mapping entry
      When the asset's location is requested
      Then the response SHALL show that email
      And SHALL mark the owner as unmapped

    Scenario: One person, one presentation
      Given a person who appears as an asset owner, as a commit author and as a resolved caller
      When each of those is presented
      Then all three SHALL show the same display name
