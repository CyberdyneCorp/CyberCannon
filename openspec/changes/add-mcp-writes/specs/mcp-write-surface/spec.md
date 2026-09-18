# Spec Delta

## Purpose

The complete set of things an automated caller may write — two proposal-shaped
tools, the identity that gates them, the two-party attribution that records them,
and the specified impossibility of a third tool — so that an agent can say "this
constraint is unreachable" and report what a validation found, without ever
becoming an author of the canon it was given to obey.

## ADDED Requirements

### Requirement: The write surface is exactly two tools

The system SHALL expose to automated callers exactly two tools that change
recorded state: one that records an observation against an asset, and one that
reports the outcome of a validation run. The advertised set SHALL be enumerated
explicitly, and any tool that changes recorded state and is not one of those two
SHALL be treated as a defect rather than an addition.

#### Scenario: Only two write tools are advertised
- **WHEN** a caller lists the tools the system offers
- **THEN** exactly two of them SHALL change recorded state
- **AND** they SHALL be the observation tool and the outcome-reporting tool

#### Scenario: No other repository content is touched by a write
- **GIVEN** a clean repository working tree
- **WHEN** an automated caller records an observation
- **THEN** the only change SHALL be the added observation on the named asset
- **AND** no other file SHALL be created, modified or deleted

### Requirement: Promotion is prohibited, not deferred

The system SHALL NOT offer an automated caller any means of promoting an
observation or an annotation into a durable rule or constraint, in this or any
future version, regardless of the roles held by the actor the caller acts as.
Promotion SHALL remain a human action taken on a human-facing surface.

#### Scenario: Art director's agent cannot promote
- **GIVEN** an automated caller acting as an actor holding the art director role
- **WHEN** it attempts to promote an observation into a rule
- **THEN** no such tool SHALL exist
- **AND** the attempt SHALL be refused

#### Scenario: Promotion is not reachable through the observation tool
- **WHEN** an observation is recorded whose text asks for a constraint to be
  changed or promoted
- **THEN** the observation SHALL be recorded as text
- **AND** no rule or constraint SHALL change as a result

### Requirement: An agent may not create an asset or a specification file

An automated caller SHALL only write against an asset that already exists in the
project. It SHALL NOT create an asset, create a specification file, or cause one
to come into existence as a side effect of a write. A write naming an unknown
asset SHALL be refused with a message that names the unknown identifier and offers
the closest existing identifiers, and SHALL NOT be recorded anywhere.

#### Scenario: Write to an unknown asset is refused
- **WHEN** an observation is recorded against an asset identifier that does not
  exist in the project
- **THEN** the write SHALL be refused naming that identifier
- **AND** no specification file SHALL be created
- **AND** the response SHALL offer the closest existing identifiers

#### Scenario: Refusal leaves the session usable
- **GIVEN** a write that was refused for naming an unknown asset
- **WHEN** the caller then reads an asset that does exist
- **THEN** the read SHALL succeed

### Requirement: Writes require an identity and reads do not

Every write SHALL require a resolved, currently valid identity. When no identity
is available, a write SHALL be refused with a message naming the action that would
make one available, and the entire read surface SHALL remain fully usable. The
validation, compilation and lookup paths SHALL NOT acquire an identity requirement
because writes exist.

#### Scenario: Unauthenticated caller keeps every read
- **GIVEN** no credential is available on the machine
- **WHEN** an automated caller reads a specification, looks up an asset's location
  and validates an export
- **THEN** every one of those SHALL succeed

#### Scenario: Unauthenticated write is refused with a remedy
- **GIVEN** no credential is available on the machine
- **WHEN** an automated caller records an observation
- **THEN** the write SHALL be refused
- **AND** the refusal SHALL name the sign-in action that would enable it

#### Scenario: Expired identity refuses the write, not the read
- **GIVEN** a credential that can no longer be refreshed
- **WHEN** the caller reads a specification and then attempts a write
- **THEN** the read SHALL succeed
- **AND** the write SHALL be refused as unverifiable

### Requirement: A credential is acquired once per machine and shared by both surfaces

The system SHALL provide a sign-in action that obtains a credential through a
device authorization flow, in which the person is shown a code and a URL,
completes authentication in a browser, and the process obtains the credential
without the person ever pasting a secret into a terminal or a configuration file.
The resulting long-lived credential SHALL be stored in the operating system's
credential store. The command-line tool and the agent-facing server SHALL read the
same stored credential, so that signing in once makes both able to write.

#### Scenario: Sign-in never asks for a pasted secret
- **WHEN** a person runs the sign-in action
- **THEN** they SHALL be shown a verification code and a URL to visit
- **AND** the flow SHALL complete without a secret being typed into the terminal

#### Scenario: One sign-in serves both surfaces
- **GIVEN** a person has signed in through the command-line tool
- **WHEN** an agent-facing server is started on the same machine as that person
- **THEN** it SHALL write as that person without a further sign-in

#### Scenario: No secret appears in configuration
- **WHEN** an agent client is configured to launch the server
- **THEN** the configuration SHALL contain no credential
- **AND** the stored credential SHALL be retrievable only from the operating
  system's credential store

#### Scenario: Signing out disables writes and leaves reads working
- **GIVEN** a signed-in machine
- **WHEN** the person signs out
- **THEN** the stored credential SHALL be removed
- **AND** subsequent writes SHALL be refused while reads continue to succeed

### Requirement: Every write is attributed to the person and to the agent

Every recorded write SHALL carry both the person it was made on behalf of and the
agent that performed it, and SHALL be rendered to humans naming both — for example
"rafa, via blender-agent". The agent's identifier SHALL come from the launch
configuration of the process, never from a tool parameter or the text of the
write.

#### Scenario: Both parties are recorded and displayed
- **GIVEN** an agent identified as `blender-agent` acting as the actor `rafa`
- **WHEN** it records an observation
- **THEN** the stored record SHALL name `rafa` as responsible and `blender-agent`
  as the instrument
- **AND** any human rendering of that record SHALL name both

#### Scenario: A claimed author in the payload is ignored
- **WHEN** a write supplies an author, actor or agent name as a parameter or in
  its text
- **THEN** the recorded attribution SHALL be the resolved person and the configured
  agent
- **AND** the supplied value SHALL have no effect on attribution

### Requirement: An unattributable write is refused, never recorded anonymously

When either the person or the agent cannot be determined, the write SHALL be
refused and nothing SHALL be recorded. The system SHALL NOT record a write with a
missing, placeholder, anonymous or system-substituted author.

#### Scenario: No resolvable person
- **WHEN** a write would be recorded with no resolvable person
- **THEN** it SHALL be refused
- **AND** no record SHALL exist afterwards

#### Scenario: No configured agent identifier
- **GIVEN** a server started without an agent identifier
- **WHEN** an automated caller attempts a write
- **THEN** the write SHALL be refused naming the missing agent identifier
- **AND** reads SHALL continue to succeed

### Requirement: An agent-authored annotation is an observation

An annotation recorded by an automated caller SHALL be an observation: it SHALL
NOT create, modify or delete any constraint, budget, rule, silhouette rule, status
or owner, and SHALL NOT resolve, promote, close or reopen any annotation,
including its own. Recording an observation that a constraint is unattainable
SHALL leave that constraint exactly as it was.

#### Scenario: Unreachable budget is recorded and the budget stands
- **GIVEN** an asset with a triangle budget of 12000
- **WHEN** an agent records that it cannot reach 12000 triangles without losing the
  head silhouette
- **THEN** the observation SHALL be recorded with that text
- **AND** the asset's triangle budget SHALL still be 12000

#### Scenario: An agent cannot close its own observation
- **GIVEN** an observation recorded by an automated caller
- **WHEN** that caller attempts to resolve or promote it
- **THEN** the attempt SHALL be refused
- **AND** the observation SHALL remain open

### Requirement: An observation declares an observation kind in its own field

An observation SHALL carry the annotation `kind` defined by the `asset-spec`
capability (`art-direction | technical | design`) — it SHALL NOT redefine, extend
or narrow that set — **and** SHALL additionally declare an `observation_kind` in a
separate field, drawn from a fixed, documented set distinguishing at least an
unattainable constraint, an ambiguity in the specification, and a defect found in
the asset. An unrecognised value in either field SHALL be refused with a message
listing the permitted values, and SHALL NOT be recorded as a free-form value.

#### Scenario: Both fields are carried
- **WHEN** an agent records an observation that a constraint is unattainable
- **THEN** the stored annotation SHALL carry a `kind` from the `asset-spec` set
- **AND** it SHALL carry `observation_kind` identifying it as an unattainable constraint
- **AND** it SHALL be filterable by either field when open annotations are read

#### Scenario: The annotation kind set is not extended
- **WHEN** an agent supplies an observation-specific value in the `kind` field
- **THEN** the write SHALL be refused naming the values `asset-spec` permits

#### Scenario: Unknown kind is refused with the permitted values
- **WHEN** an observation is recorded with a kind outside the fixed set
- **THEN** it SHALL be refused
- **AND** the refusal SHALL list the permitted kinds

### Requirement: Agent authorship is visible on every human surface

Wherever an annotation is presented to a person — a reading of open annotations, a
compiled briefing, a triage view, or a change to a specification file — an
agent-authored annotation SHALL be distinguishable from a human-authored one
without the reader inspecting anything further.

#### Scenario: Marked in a reading of open annotations
- **GIVEN** one human-authored and one agent-authored open annotation on an asset
- **WHEN** a person or an agent reads that asset's open annotations
- **THEN** the agent-authored one SHALL be marked as agent-authored
- **AND** the human-authored one SHALL NOT be

#### Scenario: Marked in the compiled briefing
- **GIVEN** an open agent-authored observation on an asset
- **WHEN** the asset's briefing is compiled
- **THEN** the observation SHALL appear as an open issue marked as agent-authored

### Requirement: An observation enters the same two-exit triage

An observation SHALL be an annotation in every respect that matters downstream: it
anchors to a target the way an annotation does, it appears among open annotations
until a human acts on it, and it has exactly the two exits every annotation has —
promoted by a person into a durable rule, or resolved by a person as an issue and
excluded from the compiled briefing. No third disposition SHALL exist for it.

#### Scenario: Resolved observation leaves the briefing
- **GIVEN** an open agent-authored observation appearing in a compiled briefing
- **WHEN** a person resolves it as an issue
- **THEN** subsequent compilations SHALL NOT contain it

#### Scenario: Promotion is recorded as the person's authorship
- **GIVEN** an agent-authored observation that a person promotes into a rule
- **WHEN** the resulting rule is read
- **THEN** it SHALL be attributed to the person who promoted it
- **AND** SHALL NOT be attributed to the agent

### Requirement: An observation anchors to a target or is recorded as unanchored

An observation SHALL be anchored to the target the caller named. When that target
cannot be resolved on the asset, the observation SHALL be recorded as unanchored
against the asset with the unresolved target preserved as given, and SHALL be
reported as unanchored when read. It SHALL NOT be silently attached to a different
target, and the write SHALL NOT be discarded for the target alone.

#### Scenario: Named target resolves
- **WHEN** an observation names a target that exists on the asset
- **THEN** the observation SHALL be anchored to that target

#### Scenario: Unresolvable target is preserved, not guessed
- **WHEN** an observation names a target that does not exist on the asset
- **THEN** the observation SHALL be recorded against the asset as unanchored
- **AND** the target as given SHALL be preserved in the record
- **AND** reading it SHALL report it as unanchored

### Requirement: A reported outcome is produced locally and locally authoritative

The verdict reported by the outcome-reporting tool SHALL be one produced by the
existing local validation behaviour, using only local files. Reporting SHALL NOT
produce, alter, re-evaluate or override a verdict, and the reported outcome SHALL
be identical to the verdict the same caller already received locally.

#### Scenario: Reporting does not change the verdict
- **GIVEN** a local validation that produced two error violations
- **WHEN** that outcome is reported
- **THEN** the reported outcome SHALL carry exactly those two violations
- **AND** the caller's local verdict SHALL be unchanged

#### Scenario: No verdict is produced by reporting
- **WHEN** the outcome-reporting tool is called
- **THEN** no validation rule SHALL be evaluated as part of the report

### Requirement: Reporting an outcome never blocks anything

A failure to deliver a reported outcome SHALL NOT change a verdict, SHALL NOT
block a commit, SHALL NOT fail a local validation run, and SHALL NOT block or
error the automated caller. An undeliverable report SHALL be retained locally and
retried later, and the caller SHALL be told that the verdict stands and delivery is
pending.

#### Scenario: Destination unreachable
- **GIVEN** the reporting destination is unreachable
- **WHEN** an outcome is reported
- **THEN** the call SHALL return successfully
- **AND** the response SHALL state that the verdict stands and delivery is pending

#### Scenario: A pre-commit run is unaffected
- **GIVEN** the reporting destination is unreachable
- **WHEN** a person validates an export as part of committing
- **THEN** the validation SHALL complete and the commit SHALL proceed on the
  verdict alone

#### Scenario: Pending reports are delivered later
- **GIVEN** an outcome retained locally because delivery failed
- **WHEN** the destination becomes reachable and delivery is next attempted
- **THEN** the retained outcome SHALL be delivered
- **AND** SHALL no longer be pending

### Requirement: Repeated reports of the same outcome do not accumulate

An outcome SHALL be identified by the asset, the exact export examined, and the
verdict's content, so that retrying or re-reporting the same run replaces the
existing record rather than adding another. A different export or a different
verdict SHALL be recorded as a new outcome.

#### Scenario: Retry does not duplicate
- **GIVEN** an outcome that was already delivered
- **WHEN** the identical outcome is reported again
- **THEN** the destination SHALL hold exactly one record of it

#### Scenario: A re-export is a new outcome
- **GIVEN** a delivered outcome for an export
- **WHEN** the asset is re-exported and the new outcome is reported
- **THEN** both outcomes SHALL be distinguishable, with the later one current

### Requirement: Writes are rate limited so an agent cannot bury a human thread

The system SHALL limit how many observations an automated caller may record within
a bounded period for a given actor and asset. On exceeding the limit the write
SHALL be refused with a message naming the limit and when writing will be possible
again, and the refusal SHALL NOT end the session or affect reads. Outcome
reporting SHALL be subject to its own limit, independent of the observation limit,
so that a validation loop cannot consume an artist's annotation allowance.

#### Scenario: A looping agent is throttled
- **GIVEN** an automated caller that has reached the observation limit for an asset
- **WHEN** it records another observation on that asset
- **THEN** the write SHALL be refused naming the limit and the time it resets
- **AND** the caller SHALL still be able to read that asset

#### Scenario: Throttling is scoped and does not stop other work
- **GIVEN** an automated caller throttled on one asset
- **WHEN** it records an observation on a different asset within that actor's limit
- **THEN** that write SHALL succeed

#### Scenario: Reporting does not consume the annotation allowance
- **GIVEN** an automated caller that has reported many outcomes
- **WHEN** it records its first observation on an asset
- **THEN** that write SHALL succeed

### Requirement: Near-duplicate observations are suppressed

When an automated caller records an observation that is materially the same as one
it already recorded and that is still open on the same asset and target, the
system SHALL NOT create a second record. It SHALL report the existing observation
instead, so that a restarted or looping agent contributes one thread rather than
many.

#### Scenario: Restarted agent does not duplicate its observation
- **GIVEN** an open agent-authored observation on an asset and target
- **WHEN** the same agent records a materially identical observation on that asset
  and target
- **THEN** no second observation SHALL be created
- **AND** the response SHALL identify the existing one

#### Scenario: A resolved observation may be raised again
- **GIVEN** an agent-authored observation that a person has resolved
- **WHEN** the agent records a materially identical observation afterwards
- **THEN** a new observation SHALL be recorded
