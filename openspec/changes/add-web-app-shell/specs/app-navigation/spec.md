# Spec Delta

## Purpose

The application's addresses and frame — how a person selects a project, reaches an
asset, understands where they are, and shares a link that still works months later.

## ADDED Requirements

### Requirement: An asset's address is its declared identifier

The address of an asset within the application SHALL be derived from the project
identifier and the asset's declared `id`. An address SHALL remain valid for as long
as the asset declares that identifier, and SHALL NOT depend on the asset's name,
its position in any listing, or any internal record identifier.

#### Scenario: A shared link still resolves after a rename
- **GIVEN** a link to an asset whose `name` is later changed
- **WHEN** the link is opened
- **THEN** it SHALL resolve to the same asset

#### Scenario: Address survives an index rebuild
- **GIVEN** a link to an asset
- **WHEN** the index is rebuilt
- **THEN** the link SHALL resolve unchanged

### Requirement: Opening an address restores the view it named

An address SHALL encode enough state that opening it reproduces what the person who
shared it was looking at — at minimum the asset and which of its surfaces was open.
State that cannot be restored SHALL degrade to the asset's default view rather than
to an error.

#### Scenario: A link to a specific surface opens it
- **WHEN** an address naming an asset's 3D surface is opened
- **THEN** that surface SHALL be shown for that asset

#### Scenario: Unrestorable state degrades
- **GIVEN** an address naming a surface that no longer exists for the asset
- **WHEN** it is opened
- **THEN** the asset's default view SHALL be shown
- **AND** the person SHALL be told why

### Requirement: Every screen states the project it belongs to

Every screen SHALL identify the project whose content it is showing. A person
SHALL NOT be able to act on an asset without the project it belongs to being
visible.

#### Scenario: Project is always visible
- **WHEN** any asset screen is shown
- **THEN** the project it belongs to SHALL be identified on that screen

### Requirement: Switching projects never carries context across

When a person switches project, the application SHALL discard the previous
project's listing, filter and search state rather than applying it to the new
project.

#### Scenario: Filters do not leak between projects
- **GIVEN** a filter applied while viewing one project
- **WHEN** the person switches to another project
- **THEN** that filter SHALL NOT be applied to the new project

#### Scenario: Switching with an asset open
- **GIVEN** an asset open in one project
- **WHEN** the person switches project
- **THEN** they SHALL be taken to that project's browser rather than to a missing asset

### Requirement: An unknown or forbidden address is distinguished

Opening an address for an asset or project that does not exist SHALL be
distinguished from one the person is not permitted to see. Neither SHALL reveal the
existence or content of anything the person may not read.

#### Scenario: Not found and not permitted are different screens
- **WHEN** an address for a non-existent asset is opened
- **THEN** the person SHALL be told it does not exist
- **AND** when an address for an asset they may not read is opened, they SHALL be
  told they do not have access, without its name or any of its content

### Requirement: The asset page is where everything about an asset converges

An asset SHALL have a single page presenting, at minimum, its identity and status,
its three owners, its effective constraints, its open annotations, its concept
views, its exports with their validation outcome, and its recorded links. Surfaces
specified by other capabilities SHALL be reached from this page.

#### Scenario: One page, everything recorded
- **WHEN** an asset's page is opened
- **THEN** it SHALL present its status, owners, effective constraints, open
  annotations, views, exports and links

#### Scenario: Absent content is stated, not hidden
- **GIVEN** an asset with no exports
- **WHEN** its page is opened
- **THEN** the page SHALL state that it has no exports rather than omitting the section
