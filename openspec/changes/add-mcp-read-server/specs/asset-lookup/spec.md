# Spec Delta

## Purpose

Answers "where is this asset" and "which assets exist" — the questions that
started the project — from a rebuildable index over the repository's
specification files, with alias-aware ranked search and no embeddings.

## ADDED Requirements

### Requirement: Locate every artifact of an asset

Given an asset identifier, the system SHALL return the locations of that asset's
artifacts: its directory in the repository, its authoring source file, its most
recent validated export, its engine content path, any recorded discussion or
design document link, and its current status together with its art, design and
code owners. Locations that are not recorded SHALL be reported as absent rather
than omitted silently.

#### Scenario: Full location answer
- **GIVEN** an asset whose specification records a source file, an engine path and
  a discussion link
- **WHEN** its location is requested
- **THEN** the response SHALL include all recorded locations, its status and its
  three owners

#### Scenario: Unrecorded location is explicit
- **GIVEN** an asset whose specification records no engine path
- **WHEN** its location is requested
- **THEN** the response SHALL state that the engine path is not recorded

#### Scenario: Validated export is identified as such
- **GIVEN** an asset with exports, one of which last passed validation
- **WHEN** its location is requested
- **THEN** the response SHALL identify which export was validated and when

### Requirement: List and filter assets

The system SHALL list the assets of a project and SHALL support filtering by
status, by owner and by tag. Listings SHALL be scoped to a single project by
default.

#### Scenario: Filter by status and owner
- **WHEN** assets are listed filtered by status `modeling` and a given art owner
- **THEN** only assets matching both SHALL be returned

### Requirement: Alias-aware ranked search

The system SHALL match a search term against an asset's identifier, name,
human-written aliases, tags and description, and SHALL rank results in the order:
exact identifier, name prefix, alias, tag, description substring. Search SHALL be
scoped to a single project by default. The system SHALL NOT require embeddings or
a vector store to serve search.

#### Scenario: Alias finds the asset
- **GIVEN** an asset named "Scout Mech" with aliases including `drone`
- **WHEN** a search for `drone` is performed
- **THEN** that asset SHALL be returned

#### Scenario: Exact identifier outranks a substring
- **GIVEN** one asset with identifier `mech_scout` and another whose description
  contains the word "mech"
- **WHEN** a search for `mech_scout` is performed
- **THEN** the asset with the exact identifier SHALL rank first

### Requirement: Zero-result queries are recorded

When a search returns no results, the system SHALL record the query term locally.
The recorded misses SHALL be retrievable, so that they can be used to decide which
aliases to add and whether richer retrieval is warranted.

#### Scenario: Miss is recorded and retrievable
- **WHEN** a search term returns no results
- **THEN** the term SHALL be recorded
- **AND** SHALL appear when recorded misses are retrieved

#### Scenario: Successful searches are not recorded as misses
- **WHEN** a search returns at least one result
- **THEN** no miss SHALL be recorded for that term

### Requirement: The index is derived and rebuildable

The lookup and search index SHALL be built by scanning the repository's
specification files, and SHALL be reconstructible in full from that scan. Deleting
the index SHALL cause no loss of project information. The system SHALL NOT treat
the index as a place where information originates.

#### Scenario: Deleted index is fully restored
- **GIVEN** an index built from a repository
- **WHEN** the index is deleted and rebuilt
- **THEN** every lookup and search SHALL return the same results as before

#### Scenario: Index is not authoritative
- **WHEN** an index entry disagrees with the specification file it was built from
- **THEN** the specification file SHALL be treated as correct

### Requirement: Stale index is detected, not silently served

The system SHALL detect when indexed specification files have changed on disk
since the index was built, and SHALL either refresh the affected entries or state
that the result may be stale. It SHALL NOT present a stale answer as current.

#### Scenario: Spec edited after indexing
- **GIVEN** an index built before a specification file was edited
- **WHEN** that asset is looked up
- **THEN** the system SHALL serve the current file content or state that the
  index is stale

### Requirement: Index maintenance is available from the command line

The system SHALL provide a command that rebuilds the index for a project and
reports how many assets were indexed and which specification files could not be
read.

#### Scenario: Rebuild reports malformed files
- **GIVEN** a project containing one malformed specification file
- **WHEN** the index is rebuilt
- **THEN** the command SHALL report the count of indexed assets and name the
  malformed file

### Requirement: Report what changed in a specification

The system SHALL report how an asset's specification has changed since a given
point in its version history, so that a consumer can discover that the contract
they built against has moved. The comparison SHALL describe changes to durable
content — concept, design and constraints — rather than reproducing the raw file
difference.

#### Scenario: Constraint changed since a revision
- **GIVEN** an asset whose triangle budget was reduced after a given revision
- **WHEN** the change since that revision is requested
- **THEN** the response SHALL state that the triangle budget changed, with its
  previous and current values

#### Scenario: No change since the revision
- **WHEN** nothing has changed since the given revision
- **THEN** the response SHALL state that the specification is unchanged
