# Spec Delta

## Purpose

Finding an asset as a human rather than as an agent — listing, filtering, searching
with the ranking the system already specifies, and being honest about why a result
appeared and about having nothing to show.

## ADDED Requirements

### Requirement: Browsing lists the project's assets with their state

The browser SHALL list the assets of the selected project, showing for each at
minimum its name, its identifier, its status and its owners. The listing SHALL be
scoped to one project.

#### Scenario: Listing shows state without opening an asset
- **WHEN** a project's assets are listed
- **THEN** each entry SHALL show its name, identifier, status and owners

### Requirement: Filtering matches the specified filters and is visible

The browser SHALL support filtering by status, by owner and by tag, using the
filters `asset-lookup` specifies. Every active filter SHALL be visible on screen and
individually removable, and the filter state SHALL be part of the address.

#### Scenario: Active filters are visible and removable
- **GIVEN** filters applied for a status and an owner
- **WHEN** the listing is shown
- **THEN** both SHALL be visible
- **AND** either SHALL be removable without clearing the other

#### Scenario: A filtered listing is shareable
- **GIVEN** a filtered listing
- **WHEN** its address is opened by another person
- **THEN** the same filters SHALL be applied

### Requirement: Search uses the specified ranking and does not reimplement it

Search SHALL present results in the order `asset-lookup` specifies and SHALL NOT
apply its own ranking, re-sorting or relevance scoring.

#### Scenario: Order comes from the specified ranking
- **GIVEN** a query matching one asset by identifier and another by description
- **WHEN** the results are shown
- **THEN** they SHALL appear in the order the specified ranking produces

### Requirement: How a result matched is disclosed

Where a result matched on something other than its name or identifier — an alias, a
tag, a description, or an unaccepted suggestion — the listing SHALL say so.

#### Scenario: Alias match is disclosed
- **GIVEN** a query matching an asset only through an alias
- **WHEN** the result is shown
- **THEN** it SHALL indicate that it matched on that alias

#### Scenario: Suggestion match is disclosed as unaccepted
- **GIVEN** a result produced only by an unaccepted suggested alias
- **WHEN** it is shown
- **THEN** it SHALL be marked as matching an unaccepted suggestion

### Requirement: An empty result is a screen, not an absence

A search returning nothing SHALL show what was searched for, state that nothing
matched, and offer a way to clear the filters. It SHALL NOT present an empty list
with no explanation.

#### Scenario: No results
- **WHEN** a search returns nothing
- **THEN** the screen SHALL state that nothing matched the query
- **AND** SHALL offer to clear any active filters

#### Scenario: Empty because of filters, not the query
- **GIVEN** a query that matches assets which the active filters exclude
- **WHEN** the results are shown
- **THEN** the screen SHALL say the filters excluded matches

### Requirement: A project with no assets explains what to do

A project containing no assets SHALL present a screen saying so and naming how an
asset comes to exist, rather than an empty listing.

#### Scenario: First run
- **WHEN** a project with no assets is opened
- **THEN** the screen SHALL state that it has no assets and how one is created

### Requirement: Degraded search is disclosed, never silently narrowed

When a search cannot be served completely — the index is rebuilding, a delegated
search is unavailable, or the working copy is stale — the browser SHALL serve what
it can and state what was unavailable. It SHALL NOT present a partial result as
complete.

#### Scenario: Index rebuilding
- **GIVEN** the index is being rebuilt
- **WHEN** a search is performed
- **THEN** results derivable without it SHALL be shown
- **AND** the screen SHALL state that results may be incomplete

#### Scenario: Delegated search unavailable
- **GIVEN** the delegated semantic search is unreachable
- **WHEN** a query is performed
- **THEN** exact results SHALL still be shown
- **AND** the screen SHALL state that the semantic results are unavailable
