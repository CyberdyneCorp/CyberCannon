# Generated from openspec/changes/improve-project-and-asset-navigation/specs/app-navigation/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:improve-project-and-asset-navigation @capability:app-navigation @spec:openspec/changes/improve-project-and-asset-navigation/specs/app-navigation/spec.md
Feature: app-navigation

  Rule: Project work areas remain reachable

    Scenario: Move from triage to the asset browser
      Given a person is on a project's triage queue
      When they activate Assets
      Then the asset browser for the same project SHALL open
      And the previous triage filters SHALL NOT be applied to the browser

    Scenario: Current work area is identified
      When a project screen is displayed
      Then its current Assets or Triage link SHALL be identified to assistive technology and visibly to the person

  Rule: Asset surfaces remain reachable

    Scenario: Move from sheet to viewer
      Given the model sheet for an asset is open
      When the person activates 3D viewer
      Then the viewer for the same project and asset SHALL open

    Scenario: Return from viewer to overview
      Given the 3D viewer for an asset is open
      When the person activates Overview
      Then the asset overview SHALL open

    Scenario: Current surface is identified
      When any asset surface is displayed
      Then its current surface link SHALL be identified to assistive technology and visibly to the person
