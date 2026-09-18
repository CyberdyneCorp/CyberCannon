# Generated from openspec/changes/add-mcp-read-server/specs/asset-lookup/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-mcp-read-server @capability:asset-lookup @spec:openspec/changes/add-mcp-read-server/specs/asset-lookup/spec.md
Feature: asset-lookup

  Rule: Locate every artifact of an asset

    Scenario: Full location answer
      Given an asset whose specification records a source file, an engine path and a discussion link
      When its location is requested
      Then the response SHALL include all recorded locations, its status and its three owners

    Scenario: Unrecorded location is explicit
      Given an asset whose specification records no engine path
      When its location is requested
      Then the response SHALL state that the engine path is not recorded

    Scenario: Validated export is identified as such
      Given an asset with exports, one of which last passed validation
      When its location is requested
      Then the response SHALL identify which export was validated and when

  Rule: List and filter assets

    Scenario: Filter by status and owner
      When assets are listed filtered by status `modeling` and a given art owner
      Then only assets matching both SHALL be returned

  Rule: Alias-aware ranked search

    Scenario: Alias finds the asset
      Given an asset named "Scout Mech" with aliases including `drone`
      When a search for `drone` is performed
      Then that asset SHALL be returned

    Scenario: Exact identifier outranks a substring
      Given one asset with identifier `mech_scout` and another whose description contains the word "mech"
      When a search for `mech_scout` is performed
      Then the asset with the exact identifier SHALL rank first

  Rule: Zero-result queries are recorded

    Scenario: Miss is recorded and retrievable
      When a search term returns no results
      Then the term SHALL be recorded
      And SHALL appear when recorded misses are retrieved

    Scenario: Successful searches are not recorded as misses
      When a search returns at least one result
      Then no miss SHALL be recorded for that term

  Rule: The index is derived and rebuildable

    Scenario: Deleted index is fully restored
      Given an index built from a repository
      When the index is deleted and rebuilt
      Then every lookup and search SHALL return the same results as before

    Scenario: Index is not authoritative
      When an index entry disagrees with the specification file it was built from
      Then the specification file SHALL be treated as correct

  Rule: Stale index is detected, not silently served

    Scenario: Spec edited after indexing
      Given an index built before a specification file was edited
      When that asset is looked up
      Then the system SHALL serve the current file content or state that the index is stale

  Rule: Index maintenance is available from the command line

    Scenario: Rebuild reports malformed files
      Given a project containing one malformed specification file
      When the index is rebuilt
      Then the command SHALL report the count of indexed assets and name the malformed file

  Rule: Report what changed in a specification

    Scenario: Constraint changed since a revision
      Given an asset whose triangle budget was reduced after a given revision
      When the change since that revision is requested
      Then the response SHALL state that the triangle budget changed, with its previous and current values

    Scenario: No change since the revision
      When nothing has changed since the given revision
      Then the response SHALL state that the specification is unchanged
