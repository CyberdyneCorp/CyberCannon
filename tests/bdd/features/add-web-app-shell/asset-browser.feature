# Generated from openspec/changes/add-web-app-shell/specs/asset-browser/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-app-shell @capability:asset-browser @spec:openspec/changes/add-web-app-shell/specs/asset-browser/spec.md
Feature: asset-browser

  Rule: Browsing lists the project's assets with their state

    Scenario: Listing shows state without opening an asset
      When a project's assets are listed
      Then each entry SHALL show its name, identifier, status and owners

  Rule: Filtering matches the specified filters and is visible

    Scenario: Active filters are visible and removable
      Given filters applied for a status and an owner
      When the listing is shown
      Then both SHALL be visible
      And either SHALL be removable without clearing the other

    Scenario: A filtered listing is shareable
      Given a filtered listing
      When its address is opened by another person
      Then the same filters SHALL be applied

  Rule: Search uses the specified ranking and does not reimplement it

    Scenario: Order comes from the specified ranking
      Given a query matching one asset by identifier and another by description
      When the results are shown
      Then they SHALL appear in the order the specified ranking produces

  Rule: How a result matched is disclosed

    Scenario: Alias match is disclosed
      Given a query matching an asset only through an alias
      When the result is shown
      Then it SHALL indicate that it matched on that alias

    Scenario: Suggestion match is disclosed as unaccepted
      Given a result produced only by an unaccepted suggested alias
      When it is shown
      Then it SHALL be marked as matching an unaccepted suggestion

  Rule: An empty result is a screen, not an absence

    Scenario: No results
      When a search returns nothing
      Then the screen SHALL state that nothing matched the query
      And SHALL offer to clear any active filters

    Scenario: Empty because of filters, not the query
      Given a query that matches assets which the active filters exclude
      When the results are shown
      Then the screen SHALL say the filters excluded matches

  Rule: A project with no assets explains what to do

    Scenario: First run
      When a project with no assets is opened
      Then the screen SHALL state that it has no assets and how one is created

  Rule: Degraded search is disclosed, never silently narrowed

    Scenario: Index rebuilding
      Given the index is being rebuilt
      When a search is performed
      Then results derivable without it SHALL be shown
      And the screen SHALL state that results may be incomplete

    Scenario: Delegated search unavailable
      Given the delegated semantic search is unreachable
      When a query is performed
      Then exact results SHALL still be shown
      And the screen SHALL state that the semantic results are unavailable
