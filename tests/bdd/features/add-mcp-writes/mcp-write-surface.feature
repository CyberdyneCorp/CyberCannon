# Generated from openspec/changes/add-mcp-writes/specs/mcp-write-surface/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-mcp-writes @capability:mcp-write-surface @spec:openspec/changes/add-mcp-writes/specs/mcp-write-surface/spec.md
Feature: mcp-write-surface

  Rule: The write surface is exactly two tools

    Scenario: Only two write tools are advertised
      When a caller lists the tools the system offers
      Then exactly two of them SHALL change recorded state
      And they SHALL be the observation tool and the outcome-reporting tool

    Scenario: No other repository content is touched by a write
      Given a clean repository working tree
      When an automated caller records an observation
      Then the only change SHALL be the added observation on the named asset
      And no other file SHALL be created, modified or deleted

  Rule: Promotion is prohibited, not deferred

    Scenario: Art director's agent cannot promote
      Given an automated caller acting as an actor holding the art director role
      When it attempts to promote an observation into a rule
      Then no such tool SHALL exist
      And the attempt SHALL be refused

    Scenario: Promotion is not reachable through the observation tool
      When an observation is recorded whose text asks for a constraint to be changed or promoted
      Then the observation SHALL be recorded as text
      And no rule or constraint SHALL change as a result

  Rule: An agent may not create an asset or a specification file

    Scenario: Write to an unknown asset is refused
      When an observation is recorded against an asset identifier that does not exist in the project
      Then the write SHALL be refused naming that identifier
      And no specification file SHALL be created
      And the response SHALL offer the closest existing identifiers

    Scenario: Refusal leaves the session usable
      Given a write that was refused for naming an unknown asset
      When the caller then reads an asset that does exist
      Then the read SHALL succeed

  Rule: Writes require an identity and reads do not

    Scenario: Unauthenticated caller keeps every read
      Given no credential is available on the machine
      When an automated caller reads a specification, looks up an asset's location and validates an export
      Then every one of those SHALL succeed

    Scenario: Unauthenticated write is refused with a remedy
      Given no credential is available on the machine
      When an automated caller records an observation
      Then the write SHALL be refused
      And the refusal SHALL name the sign-in action that would enable it

    Scenario: Expired identity refuses the write, not the read
      Given a credential that can no longer be refreshed
      When the caller reads a specification and then attempts a write
      Then the read SHALL succeed
      And the write SHALL be refused as unverifiable

  Rule: A credential is acquired once per machine and shared by both surfaces

    Scenario: Sign-in never asks for a pasted secret
      When a person runs the sign-in action
      Then they SHALL be shown a verification code and a URL to visit
      And the flow SHALL complete without a secret being typed into the terminal

    Scenario: One sign-in serves both surfaces
      Given a person has signed in through the command-line tool
      When an agent-facing server is started on the same machine as that person
      Then it SHALL write as that person without a further sign-in

    Scenario: No secret appears in configuration
      When an agent client is configured to launch the server
      Then the configuration SHALL contain no credential
      And the stored credential SHALL be retrievable only from the operating system's credential store

    Scenario: Signing out disables writes and leaves reads working
      Given a signed-in machine
      When the person signs out
      Then the stored credential SHALL be removed
      And subsequent writes SHALL be refused while reads continue to succeed

  Rule: Every write is attributed to the person and to the agent

    Scenario: Both parties are recorded and displayed
      Given an agent identified as `blender-agent` acting as the actor `rafa`
      When it records an observation
      Then the stored record SHALL name `rafa` as responsible and `blender-agent` as the instrument
      And any human rendering of that record SHALL name both

    Scenario: A claimed author in the payload is ignored
      When a write supplies an author, actor or agent name as a parameter or in its text
      Then the recorded attribution SHALL be the resolved person and the configured agent
      And the supplied value SHALL have no effect on attribution

  Rule: An unattributable write is refused, never recorded anonymously

    Scenario: No resolvable person
      When a write would be recorded with no resolvable person
      Then it SHALL be refused
      And no record SHALL exist afterwards

    Scenario: No configured agent identifier
      Given a server started without an agent identifier
      When an automated caller attempts a write
      Then the write SHALL be refused naming the missing agent identifier
      And reads SHALL continue to succeed

  Rule: An agent-authored annotation is an observation

    Scenario: Unreachable budget is recorded and the budget stands
      Given an asset with a triangle budget of 12000
      When an agent records that it cannot reach 12000 triangles without losing the head silhouette
      Then the observation SHALL be recorded with that text
      And the asset's triangle budget SHALL still be 12000

    Scenario: An agent cannot close its own observation
      Given an observation recorded by an automated caller
      When that caller attempts to resolve or promote it
      Then the attempt SHALL be refused
      And the observation SHALL remain open

  Rule: An observation declares an observation kind in its own field

    Scenario: Both fields are carried
      When an agent records an observation that a constraint is unattainable
      Then the stored annotation SHALL carry a `kind` from the `asset-spec` set
      And it SHALL carry `observation_kind` identifying it as an unattainable constraint
      And it SHALL be filterable by either field when open annotations are read

    Scenario: The annotation kind set is not extended
      When an agent supplies an observation-specific value in the `kind` field
      Then the write SHALL be refused naming the values `asset-spec` permits

    Scenario: Unknown kind is refused with the permitted values
      When an observation is recorded with a kind outside the fixed set
      Then it SHALL be refused
      And the refusal SHALL list the permitted kinds

  Rule: Agent authorship is visible on every human surface

    Scenario: Marked in a reading of open annotations
      Given one human-authored and one agent-authored open annotation on an asset
      When a person or an agent reads that asset's open annotations
      Then the agent-authored one SHALL be marked as agent-authored
      And the human-authored one SHALL NOT be

    Scenario: Marked in the compiled briefing
      Given an open agent-authored observation on an asset
      When the asset's briefing is compiled
      Then the observation SHALL appear as an open issue marked as agent-authored

  Rule: An observation enters the same two-exit triage

    Scenario: Resolved observation leaves the briefing
      Given an open agent-authored observation appearing in a compiled briefing
      When a person resolves it as an issue
      Then subsequent compilations SHALL NOT contain it

    Scenario: Promotion is recorded as the person's authorship
      Given an agent-authored observation that a person promotes into a rule
      When the resulting rule is read
      Then it SHALL be attributed to the person who promoted it
      And SHALL NOT be attributed to the agent

  Rule: An observation anchors to a target or is recorded as unanchored

    Scenario: Named target resolves
      When an observation names a target that exists on the asset
      Then the observation SHALL be anchored to that target

    Scenario: Unresolvable target is preserved, not guessed
      When an observation names a target that does not exist on the asset
      Then the observation SHALL be recorded against the asset as unanchored
      And the target as given SHALL be preserved in the record
      And reading it SHALL report it as unanchored

  Rule: A reported outcome is produced locally and locally authoritative

    Scenario: Reporting does not change the verdict
      Given a local validation that produced two error violations
      When that outcome is reported
      Then the reported outcome SHALL carry exactly those two violations
      And the caller's local verdict SHALL be unchanged

    Scenario: No verdict is produced by reporting
      When the outcome-reporting tool is called
      Then no validation rule SHALL be evaluated as part of the report

  Rule: Reporting an outcome never blocks anything

    Scenario: Destination unreachable
      Given the reporting destination is unreachable
      When an outcome is reported
      Then the call SHALL return successfully
      And the response SHALL state that the verdict stands and delivery is pending

    Scenario: A pre-commit run is unaffected
      Given the reporting destination is unreachable
      When a person validates an export as part of committing
      Then the validation SHALL complete and the commit SHALL proceed on the verdict alone

    Scenario: Pending reports are delivered later
      Given an outcome retained locally because delivery failed
      When the destination becomes reachable and delivery is next attempted
      Then the retained outcome SHALL be delivered
      And SHALL no longer be pending

  Rule: Repeated reports of the same outcome do not accumulate

    Scenario: Retry does not duplicate
      Given an outcome that was already delivered
      When the identical outcome is reported again
      Then the destination SHALL hold exactly one record of it

    Scenario: A re-export is a new outcome
      Given a delivered outcome for an export
      When the asset is re-exported and the new outcome is reported
      Then both outcomes SHALL be distinguishable, with the later one current

  Rule: Writes are rate limited so an agent cannot bury a human thread

    Scenario: A looping agent is throttled
      Given an automated caller that has reached the observation limit for an asset
      When it records another observation on that asset
      Then the write SHALL be refused naming the limit and the time it resets
      And the caller SHALL still be able to read that asset

    Scenario: Throttling is scoped and does not stop other work
      Given an automated caller throttled on one asset
      When it records an observation on a different asset within that actor's limit
      Then that write SHALL succeed

    Scenario: Reporting does not consume the annotation allowance
      Given an automated caller that has reported many outcomes
      When it records its first observation on an asset
      Then that write SHALL succeed

  Rule: Near-duplicate observations are suppressed

    Scenario: Restarted agent does not duplicate its observation
      Given an open agent-authored observation on an asset and target
      When the same agent records a materially identical observation on that asset and target
      Then no second observation SHALL be created
      And the response SHALL identify the existing one

    Scenario: A resolved observation may be raised again
      Given an agent-authored observation that a person has resolved
      When the agent records a materially identical observation afterwards
      Then a new observation SHALL be recorded
