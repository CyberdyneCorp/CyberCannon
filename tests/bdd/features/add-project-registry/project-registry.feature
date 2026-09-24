# Generated from openspec/changes/add-project-registry/specs/project-registry/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-project-registry @capability:project-registry @spec:openspec/changes/add-project-registry/specs/project-registry/spec.md
Feature: project-registry

  Rule: A deployment serves the projects its registry names

    Scenario: A registered project is served
      Given a deployment whose registry names two projects
      When either is addressed
      Then the service SHALL serve it from its own repository, branch and working copy

    Scenario: An unregistered project is not found
      When a project the registry does not name is addressed
      Then the request SHALL be refused as not found
      And the refusal SHALL NOT disclose whether that repository exists

    Scenario: Registering a project leaves the others serving
      Given a deployment serving a project
      When a second project is registered and begins cloning
      Then the first SHALL continue to answer every read throughout

  Rule: Registering a project requires authority and membership

    Scenario: A member holding none of the roles is refused
      Given a person who is a member of the deployment's organisation
      And who holds none of ART_DIRECTOR, DESIGNER or PROJECT_ADMIN
      When they attempt to register a project
      Then it SHALL be refused, naming the roles that would be required

    Scenario: A role holder from another organisation is refused
      Given a person holding PROJECT_ADMIN
      And who is not a member of the organisation this deployment serves
      When they attempt to register a project
      Then it SHALL be refused

    Scenario: Registering a repository is reserved to a person
      When a service credential attempts to register a project
      Then it SHALL be refused because the caller is not a person

  Rule: A push credential is stored encrypted and never read back

    Scenario: No read returns a credential
      Given a registered project
      When its registry entry is read by anybody
      Then the credential SHALL be absent from the answer
      And whether one is set SHALL be stated

    Scenario: A credential is replaced without being read
      Given a project whose credential no longer authenticates
      When a person with the authority to register supplies a new one
      Then it SHALL replace the stored credential
      And the previous value SHALL NOT be required or disclosed

  Rule: A configured repository seeds an empty registry

    Scenario: An existing deployment keeps working untouched
      Given a deployment configured with a repository and an empty registry
      When it starts
      Then that repository SHALL be served as a registered project
      And no operator action SHALL be required

    Scenario: A removed project is not resurrected
      Given a deployment whose configured repository was registered and then removed
      And whose registry names at least one other project
      When it restarts
      Then the removed project SHALL NOT be registered again

  Rule: The registry is exportable and importable

    Scenario: Exporting needs no key
      When the registry is exported
      Then the export SHALL carry every project and its stored credential
      And the operation SHALL NOT require the encryption key

    Scenario: Importing where the key differs says so
      Given an export taken from a deployment with a different encryption key
      When it is imported
      Then every project SHALL be restored
      And each credential SHALL be reported as unusable and requiring replacement

  Rule: Removing a project stops service, not history

    Scenario: The repository is untouched
      When a project is removed from the registry
      Then no commit, branch or file in its repository SHALL be changed
      And addressing the project SHALL be refused as not found

  Rule: The registry is the one thing a working copy cannot rebuild

    Scenario: Dropping the index leaves every project registered
      Given a deployment whose registry names two projects
      When the index is dropped entirely and rebuilt from the working copies
      Then both projects SHALL still be registered and served
      And every content answer SHALL be the same as before

    Scenario: A lost registry is not recoverable from a repository
      Given a deployment whose registry has been lost
      And whose working copies are intact
      When recovery is attempted without an export
      Then the projects SHALL NOT be reconstructed
      And the service SHALL report that the registry must be imported
