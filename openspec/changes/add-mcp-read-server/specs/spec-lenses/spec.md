# Spec Delta

## Purpose

Shapes which parts of a specification a reader receives according to the
discipline asking — so an agent needing four constraints is not handed the whole
contract — while guaranteeing that choosing a lens can never reveal more than the
caller was already entitled to.

## ADDED Requirements

### Requirement: Four discipline lenses

A specification read SHALL accept an optional lens from the set `design`, `art`,
`modeling`, `code`. Each lens SHALL return the subset of the asset's content
relevant to that discipline:

- `design` — role, states, read distance, silhouette priority, sockets, scale
  reference, and open annotations of kind `design`;
- `art` — concept description, silhouette rules, palette, views, and open
  annotations of kind `art-direction`;
- `modeling` — the effective constraints, including required sockets, and open
  annotations of kind `technical`;
- `code` — engine content path, export and validation status, sockets available
  to bind to, and recorded links.

Omitting the lens SHALL return the full specification.

#### Scenario: Modeling lens returns constraints
- **WHEN** an asset's specification is read with the `modeling` lens
- **THEN** the response SHALL contain the effective constraints and required
  sockets
- **AND** SHALL NOT contain the concept palette

#### Scenario: No lens returns everything
- **WHEN** an asset's specification is read with no lens
- **THEN** the response SHALL contain all authored blocks

#### Scenario: Unknown lens is rejected clearly
- **WHEN** a specification is read with a lens outside the defined set
- **THEN** the system SHALL refuse and name the available lenses

### Requirement: A lens narrows presentation and never widens access

A lens SHALL only remove content from what the caller is already entitled to see.
It SHALL NOT grant access to any asset, project or field that the caller could not
read without it. A caller SHALL be free to choose any lens.

#### Scenario: Lens cannot reveal an inaccessible asset
- **GIVEN** a caller not entitled to read a given project
- **WHEN** it reads an asset of that project under any lens
- **THEN** the request SHALL be refused identically for every lens

#### Scenario: Lens choice is unrestricted
- **GIVEN** a caller acting as an actor whose role is engineer
- **WHEN** it reads a specification with the `art` lens
- **THEN** the request SHALL be served

### Requirement: Required sockets are visible to the modeling lens

The `modeling` lens SHALL present sockets declared in the asset's design block as
requirements the export must satisfy, so that a modelling agent learns them before
modelling rather than at validation time.

#### Scenario: Sockets surfaced before modelling
- **GIVEN** an asset whose design declares `SOCKET_muzzle_l`
- **WHEN** its specification is read with the `modeling` lens
- **THEN** the response SHALL list `SOCKET_muzzle_l` as required in the export

### Requirement: Lenses draw from one compilation, not four

Every lens SHALL be derived from the same compiled specification, so that a field
common to two lenses has identical content in both. The system SHALL NOT maintain
a separate rendering implementation per lens.

#### Scenario: Shared field is identical across lenses
- **GIVEN** a field presented by both the `design` and `modeling` lenses
- **WHEN** the specification is read under each
- **THEN** that field's content SHALL be identical in both responses

### Requirement: Lensed reads exclude closed annotations

A lensed read SHALL include only open annotations, consistent with the compiled
specification, and SHALL NOT include annotations that were resolved or promoted.

#### Scenario: Resolved annotation absent under every lens
- **GIVEN** an asset with resolved annotations of every kind
- **WHEN** it is read under each lens in turn
- **THEN** no resolved annotation SHALL appear in any response
