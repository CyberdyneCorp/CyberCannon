# Spec Delta

## Purpose

Turns "can somebody make me a crate for the loading dock" from a message that
scrolls away into a tracked ask with an owner and an ending — raised against an
asset that exists or one that does not yet, routed to the person responsible for a
discipline, and closed by a person rather than by the asset's status changing
underneath it.

## ADDED Requirements

### Requirement: A request may target an existing asset or one that does not exist yet

A person SHALL be able to raise a request against an existing asset, and SHALL be
able to raise a request for an asset that has no specification yet by describing
what is needed. A request for a not-yet-existing asset SHALL NOT create a
specification, and SHALL become linked to one when a person creates that asset and
associates it.

#### Scenario: Request against an existing asset
- **GIVEN** an asset with a specification
- **WHEN** a person raises a request against it
- **THEN** the request SHALL be recorded referencing that asset

#### Scenario: Request for something that does not exist yet
- **WHEN** a person raises a request describing an asset that has no specification
- **THEN** the request SHALL be recorded without an asset reference
- **AND** no specification SHALL be created

#### Scenario: Linking a request to a newly created asset
- **GIVEN** an open request with no asset reference
- **WHEN** a person associates it with a newly created asset
- **THEN** the request SHALL reference that asset thereafter

#### Scenario: A request states what is needed and why
- **WHEN** a request is raised without a description of what is needed
- **THEN** it SHALL be rejected as invalid

### Requirement: A request is assigned to an owner by discipline

Every request SHALL name the discipline it concerns, and SHALL be assigned to the
person responsible for that discipline — taken from the asset's owner for that
discipline when the request targets an asset, and from the project's discipline
owners otherwise. When no owner can be determined, the request SHALL be recorded
as unassigned and reported as needing an owner, and SHALL NOT be assigned to its
author or to an arbitrary person.

#### Scenario: Assignment follows the asset's discipline owner
- **GIVEN** an asset whose modelling owner is a given person
- **WHEN** a modelling request is raised against it
- **THEN** the request SHALL be assigned to that person

#### Scenario: Assignment falls back to the project's discipline owner
- **GIVEN** a request for an asset that does not exist yet
- **WHEN** it names a discipline for which the project declares an owner
- **THEN** it SHALL be assigned to that person

#### Scenario: No owner means unassigned, not misassigned
- **GIVEN** a discipline with no owner on the asset and none on the project
- **WHEN** a request for it is raised
- **THEN** the request SHALL be recorded as unassigned
- **AND** SHALL be reported as needing an owner

#### Scenario: Reassignment is attributed
- **WHEN** a request is reassigned to another person
- **THEN** the change SHALL record who reassigned it and when

### Requirement: A request has an explicit lifecycle ending in a terminal state

A request SHALL occupy exactly one of the states `open`, `accepted`, `fulfilled`,
`declined` and `withdrawn`. The permitted transitions SHALL be `open → accepted`,
`open → declined`, `open → withdrawn`, `accepted → fulfilled`,
`accepted → declined` and `accepted → withdrawn`. `fulfilled`, `declined` and
`withdrawn` SHALL be terminal. Any other transition SHALL be refused, a `declined`
request SHALL carry a stated reason, and only the request's author SHALL be able
to withdraw it.

#### Scenario: Invalid transition is refused
- **GIVEN** a request in the `fulfilled` state
- **WHEN** a transition back to `open` is attempted
- **THEN** it SHALL be refused
- **AND** the request SHALL remain `fulfilled`

#### Scenario: Declining states a reason
- **WHEN** a request is declined without a reason
- **THEN** the transition SHALL be refused

#### Scenario: Only the author withdraws
- **GIVEN** a request raised by one person
- **WHEN** another person attempts to withdraw it
- **THEN** the attempt SHALL be refused

#### Scenario: Every transition is attributed
- **WHEN** a request changes state
- **THEN** the record SHALL identify the person who caused the change and when

### Requirement: A request observes the asset status lifecycle and never drives it

Accepting, fulfilling or declining a request SHALL NOT change the status of any
asset, and changing an asset's status SHALL NOT change the state of any request. A
request MAY declare the asset status it is asking for, and when it does, it SHALL
be markable as `fulfilled` only once the referenced asset has reached that status.

#### Scenario: Request state does not move asset status
- **GIVEN** an asset in the `modeling` status with an accepted request against it
- **WHEN** the request is marked `fulfilled`
- **THEN** the asset's status SHALL be unchanged

#### Scenario: Asset status does not move request state
- **GIVEN** an open request against an asset
- **WHEN** the asset's status advances
- **THEN** the request SHALL remain `open`

#### Scenario: Fulfilment requires the asked-for status
- **GIVEN** a request asking for an asset to reach `validated` and an asset in
  `modeling`
- **WHEN** the request is marked `fulfilled`
- **THEN** the transition SHALL be refused naming the asset's current status

#### Scenario: Fulfilment succeeds once the status is reached
- **GIVEN** the same request and an asset that has reached `validated`
- **WHEN** the request is marked `fulfilled`
- **THEN** the transition SHALL succeed

### Requirement: Requests are durable repository content, not index rows

A request and its full state history SHALL be stored such that they survive the
loss and rebuild of the service's index. Dropping the index and rebuilding it
SHALL restore every request, its assignment, its state and its attribution
unchanged.

#### Scenario: Requests survive an index rebuild
- **GIVEN** a project with open, accepted and terminal requests
- **WHEN** the index is dropped and rebuilt
- **THEN** every request SHALL be present with the same state, assignee and
  attribution

#### Scenario: A request that could not be persisted did not happen
- **GIVEN** a request whose persistence to the repository failed
- **WHEN** the project's requests are listed
- **THEN** that request SHALL NOT appear
- **AND** its author SHALL have been told it was not recorded

### Requirement: Raising a request needs read access; deciding one needs responsibility

Any actor permitted to read a project SHALL be permitted to raise a request within
it. Accepting, declining or fulfilling a request SHALL be permitted only to its
assignee or to an actor holding the role responsible for that discipline, and
SHALL be refused to every other actor with a message naming what would be
required. These decisions SHALL be made by domain policy rather than by the
networked surface.

#### Scenario: A reader may ask
- **GIVEN** an actor permitted only to read a project
- **WHEN** they raise a request
- **THEN** it SHALL be recorded

#### Scenario: An unrelated actor may not decide
- **GIVEN** an actor who is neither the assignee nor a holder of the responsible
  role
- **WHEN** they attempt to accept a request
- **THEN** the attempt SHALL be refused naming the required role

#### Scenario: A request is not a constraint
- **WHEN** a request is raised, accepted or fulfilled
- **THEN** no constraint, silhouette rule or other durable specification content
  SHALL be created or changed by that act alone

### Requirement: Notification of a request is in-app, minimal and never blocking

When a request is assigned to a person or changes state, that person and the
request's author SHALL be able to see it as an unread item within the application.
Notification SHALL be readable, dismissible and countable, SHALL NOT be delivered
by electronic mail or device push, and a failure to record a notification SHALL
NOT fail or reverse the action that caused it.

#### Scenario: Assignee sees an unread item
- **GIVEN** a request assigned to a person
- **WHEN** that person's unread items are listed
- **THEN** the request SHALL appear among them

#### Scenario: Dismissal is per person
- **GIVEN** a notification visible to two people
- **WHEN** one of them dismisses it
- **THEN** it SHALL remain unread for the other

#### Scenario: Notification failure does not reverse the action
- **GIVEN** notification recording is failing
- **WHEN** a request is accepted
- **THEN** the acceptance SHALL stand
- **AND** the caller SHALL NOT receive a failure
