# Spec Delta

## Purpose

Establishes that an automated caller acts as a person rather than holding a role
of its own — how it is identified, what it may do, how its actions are recorded,
and the things no agent may do regardless of who it acts as. It also binds a
person's two identities, the authenticated subject and the git commit author,
into one actor, so that attribution survives the fact that the source of truth is
a git repository.

## ADDED Requirements

### Requirement: Identity comes from the credential, never from a parameter

The identity a caller acts as SHALL be derived solely from the credential the
process was launched with. The system SHALL NOT accept an actor identifier, role,
group, project or permission supplied as a tool parameter, a request field or an
environment hint, and SHALL ignore any such value if present.

#### Scenario: Claimed role is ignored
- **GIVEN** a caller whose credential resolves to an actor holding the artist role
- **WHEN** it supplies a parameter claiming the art director role
- **THEN** the system SHALL evaluate the request as the artist
- **AND** the supplied claim SHALL have no effect

#### Scenario: Claimed identity is ignored
- **WHEN** a caller supplies an actor identifier differing from its credential
- **THEN** the system SHALL use the credential's actor

### Requirement: An agent acts as a person and never escalates

A caller SHALL be permitted exactly what the actor it acts as is permitted, and
nothing more. There SHALL be no role, permission or capability that exists only
for automated callers.

#### Scenario: Agent denied what its person is denied
- **GIVEN** an actor who may not read a given project
- **WHEN** an agent acting as that actor requests an asset from that project
- **THEN** the request SHALL be refused

### Requirement: The credential's format never reaches the core

Authorization decisions SHALL be made against a resolved actor with an identifier
and a set of roles. The representation of the credential — its encoding, claim
names, group names or issuing service — SHALL NOT be visible to the decision, so
that authorization behaviour can be verified without an identity service running.

#### Scenario: Authorization verified without an identity service
- **GIVEN** no identity service is reachable
- **WHEN** an authorization decision is evaluated for a resolved actor
- **THEN** the decision SHALL be produced from the actor's roles alone

### Requirement: Reads degrade to a local actor when no identity is configured

When no credential is configured, the system SHALL resolve a local unauthenticated
actor that may read the project on the machine, and SHALL NOT refuse reads for
lack of identity. Actions that require a role SHALL be refused for that actor with
a message naming what would be required.

#### Scenario: Read works with no credential
- **GIVEN** no credential is configured
- **WHEN** an agent reads an asset's specification
- **THEN** the read SHALL succeed

#### Scenario: Role-requiring action refused with a reason
- **GIVEN** no credential is configured
- **WHEN** an action requiring a role is attempted
- **THEN** it SHALL be refused with a message naming the required role

### Requirement: Identity outage degrades rather than blocks

When a previously resolved actor cannot be refreshed because the identity service
is unreachable, the system SHALL continue to serve reads using the last resolved
actor for a bounded period, and SHALL refuse only the actions that require a role
to be currently verified.

#### Scenario: Reads survive an identity outage
- **GIVEN** an actor resolved earlier and an identity service now unreachable
- **WHEN** that caller reads an asset
- **THEN** the read SHALL succeed

#### Scenario: Cached actor expires
- **GIVEN** a cached actor older than the permitted period
- **WHEN** a role-requiring action is attempted
- **THEN** it SHALL be refused as unverifiable

### Requirement: Actions are attributed to the person and the agent

Any action recorded by the system on behalf of an automated caller SHALL record
both the actor it acted as and the agent that performed it, so that the record
identifies an accountable person and the instrument used. An action SHALL NOT be
attributed to an agent alone.

#### Scenario: Attribution names both
- **WHEN** an action is recorded for an agent acting as a given actor
- **THEN** the record SHALL identify that actor as responsible
- **AND** SHALL identify the agent as the instrument

#### Scenario: Unattributable action is refused
- **WHEN** an action would be recorded with no resolvable actor
- **THEN** it SHALL be refused rather than recorded anonymously

### Requirement: Agents never author constraints

No automated caller SHALL create, modify or delete a constraint, a silhouette
rule, or any other durable content of a specification, regardless of the roles
held by the actor it acts as. An automated caller MAY report that a constraint is
unattainable; that report SHALL be recorded as an observation and SHALL NOT alter
the constraint.

#### Scenario: Unattainable budget is reported, not changed
- **GIVEN** an asset with a triangle budget an agent cannot meet
- **WHEN** the agent reports that the budget is unattainable
- **THEN** the report SHALL be recorded as an observation
- **AND** the recorded triangle budget SHALL be unchanged

#### Scenario: Constraint edit refused for every role
- **WHEN** an automated caller attempts to modify a constraint while acting as an
  actor holding any role
- **THEN** the attempt SHALL be refused

### Requirement: Autonomous runs are attributed as automation

A run with no live human caller SHALL authenticate as the system itself, SHALL be
attributed as automation rather than as any person, and SHALL be denied every
action that requires a human actor.

#### Scenario: Scheduled run cannot act as a person
- **GIVEN** a run with no human caller
- **WHEN** it performs a recorded action
- **THEN** the record SHALL identify it as automation
- **AND** SHALL NOT name any person as responsible

### Requirement: A project records the mapping between identity subjects and git authors

A project SHALL carry an actor mapping, authored in the repository at
`.canon/actors.yaml`, in which each entry binds one identity subject to a display
name, one or more git author email addresses, an optional chat handle, and a
default role drawn from the defined role set. An entry's identity subject and its
git author emails SHALL denote the same person, so that the person an identity
provider authenticated and the person who authored a commit are recognised as one
actor rather than two. A project without a mapping SHALL remain fully readable.

#### Scenario: One entry binds both identities
- **GIVEN** an entry binding the subject `auth|rafa` to the display name `Rafa`,
  the git emails `rafa@cyberdyne.com` and `rafa@personal.dev`, and the default
  role `ARTIST`
- **WHEN** either that subject or either email is resolved to an actor
- **THEN** the same actor SHALL be returned, carrying that display name and that
  default role

#### Scenario: A project without a mapping still works
- **GIVEN** a project that has no actor mapping
- **WHEN** an asset's specification is read
- **THEN** the read SHALL succeed
- **AND** every git author encountered SHALL resolve as unmapped

### Requirement: Git authors and actors resolve in both directions

The system SHALL resolve a git commit author email to the actor it belongs to,
and SHALL resolve an actor to the git author identity — display name and email —
to be used when a change is committed on that person's behalf. Both directions
SHALL be answered from the same mapping, so the two answers cannot disagree.
Email comparison SHALL be case-insensitive. When an actor lists several emails,
the first listed SHALL be the one used for changes committed on their behalf.

#### Scenario: Commit author is recognised as the person
- **GIVEN** a mapping entry listing the email `rafa@cyberdyne.com`
- **WHEN** a commit authored by `RAFA@Cyberdyne.com` is resolved
- **THEN** it SHALL resolve to that entry's actor

#### Scenario: Git identity for acting on a person's behalf
- **GIVEN** an actor whose entry lists `rafa@cyberdyne.com` then `rafa@personal.dev`
- **WHEN** the git author identity for that actor is requested
- **THEN** it SHALL be that actor's display name with `rafa@cyberdyne.com`

#### Scenario: Round trip is stable
- **WHEN** an actor is resolved to a git author identity and that identity's email
  is resolved back to an actor
- **THEN** the original actor SHALL be returned

### Requirement: An unmapped git author resolves to an explicitly unknown actor

When a git author email matches no entry in the mapping, the system SHALL resolve
it to an actor that is explicitly marked unknown, carrying the original email
verbatim and holding no roles. The system SHALL NOT drop the authorship, SHALL
NOT substitute the closest matching actor, and SHALL NOT attribute it to the
caller or to any other person. Every presentation of such an actor SHALL mark it
as unmapped, and the distinct unmapped authors of a project SHALL be retrievable
so that the mapping can be completed.

#### Scenario: Unmapped author is preserved and flagged
- **GIVEN** a commit authored by an email present in no mapping entry
- **WHEN** its author is resolved
- **THEN** an explicitly unknown actor SHALL be returned carrying that email
- **AND** any response naming it SHALL mark it as unmapped

#### Scenario: A near miss is never guessed
- **GIVEN** a mapping entry listing `rafa@cyberdyne.com`
- **WHEN** a commit authored by `r.santos@cyberdyne.com` is resolved
- **THEN** the result SHALL be an unknown actor
- **AND** SHALL NOT be the actor holding `rafa@cyberdyne.com`

#### Scenario: Unmapped authors are enumerable
- **GIVEN** a project whose history contains two authors absent from the mapping
- **WHEN** the project's unmapped authors are requested
- **THEN** both emails SHALL be listed

### Requirement: The actor mapping is authored content and is validated structurally

The actor mapping SHALL be a file in the repository, versioned, diffable and
reviewable in the same way as any other authored specification content, and its
validation SHALL require neither identity nor network. Validation SHALL report a
violation when the same identity subject appears in more than one entry, when the
same git author email appears in more than one entry, when an entry declares a
default role outside the defined role set, when an entry declares no git author
email, and when the mapping cannot be parsed. Each violation SHALL name the
offending entry and SHALL carry the same identifier, severity, message and
subject as any other validation violation.

#### Scenario: Duplicate email is a violation
- **GIVEN** two entries that both list `rafa@cyberdyne.com`
- **WHEN** the mapping is validated
- **THEN** a violation SHALL be reported naming that email and both entries

#### Scenario: Duplicate subject is a violation
- **GIVEN** two entries that declare the same identity subject
- **WHEN** the mapping is validated
- **THEN** a violation SHALL be reported naming that subject

#### Scenario: Unknown role is a violation
- **GIVEN** an entry whose default role is outside the defined role set
- **WHEN** the mapping is validated
- **THEN** a violation SHALL be reported naming the entry and the available roles

#### Scenario: Mapping validation needs nothing external
- **GIVEN** no identity service is reachable and the machine has no network
- **WHEN** the mapping is validated
- **THEN** validation SHALL complete and report its violations normally

### Requirement: Provider claims take precedence over the mapping file

When a resolved actor's identity provider supplies the link between the subject
and its git author emails, the system SHALL use the provider's values and SHALL
NOT consult the mapping file for that actor. The file SHALL be consulted only for
people the provider does not describe, and whenever no provider is configured or
reachable. Where the provider and the file both describe the same person and
disagree, the provider's values SHALL be used and the disagreement SHALL be
reported, so the file remains a fallback rather than a second source of truth.

#### Scenario: Provider-supplied emails win
- **GIVEN** a provider that resolves an actor together with its git author emails
- **WHEN** that actor's git author identity is requested
- **THEN** the provider's emails SHALL be used
- **AND** the mapping file SHALL NOT change the result

#### Scenario: The file answers what the provider does not
- **GIVEN** a provider that resolves an actor but supplies no git author emails
- **WHEN** that actor's git author identity is requested
- **THEN** the emails SHALL come from the mapping file entry for that subject

#### Scenario: Disagreement is surfaced
- **GIVEN** a provider and a mapping file that bind the same subject to different
  git author emails
- **WHEN** that actor is resolved
- **THEN** the provider's emails SHALL be used
- **AND** the system SHALL report that the mapping file entry disagrees

### Requirement: Attribution is presented through the resolved actor

Every response that names an owner, an author or a responsible person — including
the location answer for an asset and any listing that names owners — SHALL
present the resolved actor's display name rather than a raw identity subject or a
raw email address, and SHALL mark the name as unmapped when it resolved to an
unknown actor. The same person SHALL be presented identically whether the name
originated from a provider claim, from the mapping file, or from a git commit
author.

#### Scenario: A location answer names the person
- **GIVEN** an asset whose art owner is recorded as `rafa@cyberdyne.com` and a
  mapping entry binding that email to the display name `Rafa`
- **WHEN** the asset's location is requested
- **THEN** the response SHALL name the art owner as `Rafa`

#### Scenario: An unmapped owner is shown as unmapped
- **GIVEN** an asset whose art owner is an email present in no mapping entry
- **WHEN** the asset's location is requested
- **THEN** the response SHALL show that email
- **AND** SHALL mark the owner as unmapped

#### Scenario: One person, one presentation
- **GIVEN** a person who appears as an asset owner, as a commit author and as a
  resolved caller
- **WHEN** each of those is presented
- **THEN** all three SHALL show the same display name
