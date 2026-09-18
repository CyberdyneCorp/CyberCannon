# Generated from openspec/changes/add-mcp-read-server/specs/spec-lenses/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-mcp-read-server @capability:spec-lenses @spec:openspec/changes/add-mcp-read-server/specs/spec-lenses/spec.md
Feature: spec-lenses

  Rule: Four discipline lenses

    Scenario: Modeling lens returns constraints
      When an asset's specification is read with the `modeling` lens
      Then the response SHALL contain the effective constraints and required sockets
      And SHALL NOT contain the concept palette

    Scenario: No lens returns everything
      When an asset's specification is read with no lens
      Then the response SHALL contain all authored blocks

    Scenario: Unknown lens is rejected clearly
      When a specification is read with a lens outside the defined set
      Then the system SHALL refuse and name the available lenses

  Rule: A lens narrows presentation and never widens access

    Scenario: Lens cannot reveal an inaccessible asset
      Given a caller not entitled to read a given project
      When it reads an asset of that project under any lens
      Then the request SHALL be refused identically for every lens

    Scenario: Lens choice is unrestricted
      Given a caller acting as an actor whose role is engineer
      When it reads a specification with the `art` lens
      Then the request SHALL be served

  Rule: Required sockets are visible to the modeling lens

    Scenario: Sockets surfaced before modelling
      Given an asset whose design declares `SOCKET_muzzle_l`
      When its specification is read with the `modeling` lens
      Then the response SHALL list `SOCKET_muzzle_l` as required in the export

  Rule: Lenses draw from one compilation, not four

    Scenario: Shared field is identical across lenses
      Given a field presented by both the `design` and `modeling` lenses
      When the specification is read under each
      Then that field's content SHALL be identical in both responses

  Rule: Lensed reads exclude closed annotations

    Scenario: Resolved annotation absent under every lens
      Given an asset with resolved annotations of every kind
      When it is read under each lens in turn
      Then no resolved annotation SHALL appear in any response
