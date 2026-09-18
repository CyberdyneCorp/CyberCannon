# Generated from openspec/changes/add-web-backend/specs/asset-requests/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-backend @capability:asset-requests @spec:openspec/changes/add-web-backend/specs/asset-requests/spec.md
Feature: asset-requests

  Rule: A request may target an existing asset or one that does not exist yet

    Scenario: Request against an existing asset
      Given an asset with a specification
      When a person raises a request against it
      Then the request SHALL be recorded referencing that asset

    Scenario: Request for something that does not exist yet
      When a person raises a request describing an asset that has no specification
      Then the request SHALL be recorded without an asset reference
      And no specification SHALL be created

    Scenario: Linking a request to a newly created asset
      Given an open request with no asset reference
      When a person associates it with a newly created asset
      Then the request SHALL reference that asset thereafter

    Scenario: A request states what is needed and why
      When a request is raised without a description of what is needed
      Then it SHALL be rejected as invalid

  Rule: A request is assigned to an owner by discipline

    Scenario: Assignment follows the asset's discipline owner
      Given an asset whose modelling owner is a given person
      When a modelling request is raised against it
      Then the request SHALL be assigned to that person

    Scenario: Assignment falls back to the project's discipline owner
      Given a request for an asset that does not exist yet
      When it names a discipline for which the project declares an owner
      Then it SHALL be assigned to that person

    Scenario: No owner means unassigned, not misassigned
      Given a discipline with no owner on the asset and none on the project
      When a request for it is raised
      Then the request SHALL be recorded as unassigned
      And SHALL be reported as needing an owner

    Scenario: Reassignment is attributed
      When a request is reassigned to another person
      Then the change SHALL record who reassigned it and when

  Rule: A request has an explicit lifecycle ending in a terminal state

    Scenario: Invalid transition is refused
      Given a request in the `fulfilled` state
      When a transition back to `open` is attempted
      Then it SHALL be refused
      And the request SHALL remain `fulfilled`

    Scenario: Declining states a reason
      When a request is declined without a reason
      Then the transition SHALL be refused

    Scenario: Only the author withdraws
      Given a request raised by one person
      When another person attempts to withdraw it
      Then the attempt SHALL be refused

    Scenario: Every transition is attributed
      When a request changes state
      Then the record SHALL identify the person who caused the change and when

  Rule: A request observes the asset status lifecycle and never drives it

    Scenario: Request state does not move asset status
      Given an asset in the `modeling` status with an accepted request against it
      When the request is marked `fulfilled`
      Then the asset's status SHALL be unchanged

    Scenario: Asset status does not move request state
      Given an open request against an asset
      When the asset's status advances
      Then the request SHALL remain `open`

    Scenario: Fulfilment requires the asked-for status
      Given a request asking for an asset to reach `validated` and an asset in `modeling`
      When the request is marked `fulfilled`
      Then the transition SHALL be refused naming the asset's current status

    Scenario: Fulfilment succeeds once the status is reached
      Given the same request and an asset that has reached `validated`
      When the request is marked `fulfilled`
      Then the transition SHALL succeed

  Rule: Requests are durable repository content, not index rows

    Scenario: Requests survive an index rebuild
      Given a project with open, accepted and terminal requests
      When the index is dropped and rebuilt
      Then every request SHALL be present with the same state, assignee and attribution

    Scenario: A request that could not be persisted did not happen
      Given a request whose persistence to the repository failed
      When the project's requests are listed
      Then that request SHALL NOT appear
      And its author SHALL have been told it was not recorded

  Rule: Raising a request needs read access; deciding one needs responsibility

    Scenario: A reader may ask
      Given an actor permitted only to read a project
      When they raise a request
      Then it SHALL be recorded

    Scenario: An unrelated actor may not decide
      Given an actor who is neither the assignee nor a holder of the responsible role
      When they attempt to accept a request
      Then the attempt SHALL be refused naming the required role

    Scenario: A request is not a constraint
      When a request is raised, accepted or fulfilled
      Then no constraint, silhouette rule or other durable specification content SHALL be created or changed by that act alone

  Rule: Notification of a request is in-app, minimal and never blocking

    Scenario: Assignee sees an unread item
      Given a request assigned to a person
      When that person's unread items are listed
      Then the request SHALL appear among them

    Scenario: Dismissal is per person
      Given a notification visible to two people
      When one of them dismisses it
      Then it SHALL remain unread for the other

    Scenario: Notification failure does not reverse the action
      Given notification recording is failing
      When a request is accepted
      Then the acceptance SHALL stand
      And the caller SHALL NOT receive a failure
