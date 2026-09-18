# Generated from openspec/changes/add-web-app-shell/specs/app-navigation/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-app-shell @capability:app-navigation @spec:openspec/changes/add-web-app-shell/specs/app-navigation/spec.md
Feature: app-navigation

  Rule: An asset's address is its declared identifier

    Scenario: A shared link still resolves after a rename
      Given a link to an asset whose `name` is later changed
      When the link is opened
      Then it SHALL resolve to the same asset

    Scenario: Address survives an index rebuild
      Given a link to an asset
      When the index is rebuilt
      Then the link SHALL resolve unchanged

  Rule: Opening an address restores the view it named

    Scenario: A link to a specific surface opens it
      When an address naming an asset's 3D surface is opened
      Then that surface SHALL be shown for that asset

    Scenario: Unrestorable state degrades
      Given an address naming a surface that no longer exists for the asset
      When it is opened
      Then the asset's default view SHALL be shown
      And the person SHALL be told why

  Rule: Every screen states the project it belongs to

    Scenario: Project is always visible
      When any asset screen is shown
      Then the project it belongs to SHALL be identified on that screen

  Rule: Switching projects never carries context across

    Scenario: Filters do not leak between projects
      Given a filter applied while viewing one project
      When the person switches to another project
      Then that filter SHALL NOT be applied to the new project

    Scenario: Switching with an asset open
      Given an asset open in one project
      When the person switches project
      Then they SHALL be taken to that project's browser rather than to a missing asset

  Rule: An unknown or forbidden address is distinguished

    Scenario: Not found and not permitted are different screens
      When an address for a non-existent asset is opened
      Then the person SHALL be told it does not exist
      And when an address for an asset they may not read is opened, they SHALL be told they do not have access, without its name or any of its content

  Rule: The asset page is where everything about an asset converges

    Scenario: One page, everything recorded
      When an asset's page is opened
      Then it SHALL present its status, owners, effective constraints, open annotations, views, exports and links

    Scenario: Absent content is stated, not hidden
      Given an asset with no exports
      When its page is opened
      Then the page SHALL state that it has no exports rather than omitting the section
