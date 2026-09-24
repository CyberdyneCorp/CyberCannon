# Spec Delta

## Purpose

Which game repositories a deployment serves, who may add one, and how the one
piece of state no repository can rebuild is protected and recovered.

## ADDED Requirements

### Requirement: A deployment serves the projects its registry names

The service SHALL serve every project its registry names, and SHALL serve no
project it does not name. Each entry SHALL carry the project's identifier, the
repository it is read from, the branch write-backs are committed to, and the
credential the service authenticates to that repository with. Registering,
changing or removing one project SHALL NOT interrupt the service of another.

#### Scenario: A registered project is served
- **GIVEN** a deployment whose registry names two projects
- **WHEN** either is addressed
- **THEN** the service SHALL serve it from its own repository, branch and working copy

#### Scenario: An unregistered project is not found
- **WHEN** a project the registry does not name is addressed
- **THEN** the request SHALL be refused as not found
- **AND** the refusal SHALL NOT disclose whether that repository exists

#### Scenario: Registering a project leaves the others serving
- **GIVEN** a deployment serving a project
- **WHEN** a second project is registered and begins cloning
- **THEN** the first SHALL continue to answer every read throughout

### Requirement: Registering a project requires authority and membership

The service SHALL permit a person to register, change or remove a project only
when they hold ART_DIRECTOR, DESIGNER or PROJECT_ADMIN **and** are a member of
the organisation the deployment serves. Both SHALL be required: neither a role
without membership nor membership without one of those roles SHALL suffice.
Automation SHALL NOT register, change or remove a project, whatever it holds.

#### Scenario: A member holding none of the roles is refused
- **GIVEN** a person who is a member of the deployment's organisation
- **AND** who holds none of ART_DIRECTOR, DESIGNER or PROJECT_ADMIN
- **WHEN** they attempt to register a project
- **THEN** it SHALL be refused, naming the roles that would be required

#### Scenario: A role holder from another organisation is refused
- **GIVEN** a person holding PROJECT_ADMIN
- **AND** who is not a member of the organisation this deployment serves
- **WHEN** they attempt to register a project
- **THEN** it SHALL be refused

#### Scenario: Registering a repository is reserved to a person
- **WHEN** a service credential attempts to register a project
- **THEN** it SHALL be refused because the caller is not a person

### Requirement: A push credential is stored encrypted and never read back

A project's credential SHALL be stored encrypted, and SHALL NOT be returned by
any read, rendered in any response, or written to any log, message or traceback.
It SHALL be replaceable by a person with the authority to register a project,
and replacing it SHALL NOT require the previous value.

#### Scenario: No read returns a credential
- **GIVEN** a registered project
- **WHEN** its registry entry is read by anybody
- **THEN** the credential SHALL be absent from the answer
- **AND** whether one is set SHALL be stated

#### Scenario: A credential is replaced without being read
- **GIVEN** a project whose credential no longer authenticates
- **WHEN** a person with the authority to register supplies a new one
- **THEN** it SHALL replace the stored credential
- **AND** the previous value SHALL NOT be required or disclosed

### Requirement: A configured repository seeds an empty registry

Where the deployment is configured with a repository and the registry names no
project, the service SHALL register that repository as a project and serve it.
It SHALL do so only while the registry is empty, so that a project removed
deliberately is not restored by a restart.

#### Scenario: An existing deployment keeps working untouched
- **GIVEN** a deployment configured with a repository and an empty registry
- **WHEN** it starts
- **THEN** that repository SHALL be served as a registered project
- **AND** no operator action SHALL be required

#### Scenario: A removed project is not resurrected
- **GIVEN** a deployment whose configured repository was registered and then removed
- **AND** whose registry names at least one other project
- **WHEN** it restarts
- **THEN** the removed project SHALL NOT be registered again

### Requirement: The registry is exportable and importable

The service SHALL provide an operation that exports the whole registry, and one
that imports such an export. The export SHALL carry each credential exactly as
stored and SHALL NOT require the means to decrypt it. Importing into a
deployment holding the same encryption key SHALL restore every project and its
credential; importing into one holding a different key SHALL restore every
project and SHALL report each credential as unusable rather than appearing to
restore it.

#### Scenario: Exporting needs no key
- **WHEN** the registry is exported
- **THEN** the export SHALL carry every project and its stored credential
- **AND** the operation SHALL NOT require the encryption key

#### Scenario: Importing where the key differs says so
- **GIVEN** an export taken from a deployment with a different encryption key
- **WHEN** it is imported
- **THEN** every project SHALL be restored
- **AND** each credential SHALL be reported as unusable and requiring replacement

### Requirement: Removing a project stops service, not history

Removing a project SHALL stop the service answering for it and SHALL NOT modify
or delete the repository. Its working copy MAY be reclaimed, and anything the
index held for it SHALL be discarded.

#### Scenario: The repository is untouched
- **WHEN** a project is removed from the registry
- **THEN** no commit, branch or file in its repository SHALL be changed
- **AND** addressing the project SHALL be refused as not found

### Requirement: The registry is the one thing a working copy cannot rebuild

`hosted-repository` requires that every answer the service gives SHALL be
derivable from the working copy alone, and that the index is never
authoritative. That requirement stands for every answer about a project's
**content**. The registry is excepted, and the exception is exact: it names the
repositories the working copies are made from, so it cannot be derived from
them without circularity.

The registry SHALL hold nothing but what identifies a project and reaches its
repository. No answer about an asset, an annotation, a request, a status or a
link SHALL depend on it beyond deciding which repository to read. A deployment
that has lost its registry SHALL recover it by import, and SHALL NOT be able to
rebuild it from any repository.

#### Scenario: Dropping the index leaves every project registered
- **GIVEN** a deployment whose registry names two projects
- **WHEN** the index is dropped entirely and rebuilt from the working copies
- **THEN** both projects SHALL still be registered and served
- **AND** every content answer SHALL be the same as before

#### Scenario: A lost registry is not recoverable from a repository
- **GIVEN** a deployment whose registry has been lost
- **AND** whose working copies are intact
- **WHEN** recovery is attempted without an export
- **THEN** the projects SHALL NOT be reconstructed
- **AND** the service SHALL report that the registry must be imported
