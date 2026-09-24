# Generated from openspec/changes/compact-asset-workspace/specs/asset-workspace-layout/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:compact-asset-workspace @capability:asset-workspace-layout @spec:openspec/changes/compact-asset-workspace/specs/asset-workspace-layout/spec.md
Feature: asset-workspace-layout

  Rule: Responsive asset inspection workspace

    Scenario: Wide asset viewer
      When a reviewer opens a 3D asset viewer on a wide screen
      Then the model viewport expands into the main column, and parts and animation appear in an adjacent tool column

    Scenario: Narrow asset viewer
      When a reviewer opens the viewer on a narrow screen
      Then model, tools, and annotations form one readable column with no horizontal page overflow

  Rule: Compact asset facts and discussions

    Scenario: Wide asset overview
      When a reviewer opens an asset overview on a wide screen
      Then its fact sections occupy responsive balanced columns

    Scenario: Viewer discussion
      When a reviewer opens a thread in the wide viewer
      Then the thread list and selected discussion remain visible in adjacent regions
