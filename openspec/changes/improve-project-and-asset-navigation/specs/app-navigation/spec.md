# Spec Delta

## Purpose

The application navigation lets a person move between a project's work areas and an asset's surfaces while keeping the current context and shareable address clear.

## ADDED Requirements

### Requirement: Project work areas remain reachable

On every project screen, the application SHALL provide direct links to that project's asset browser and triage queue. It SHALL identify the current work area without relying on color alone.

#### Scenario: Move from triage to the asset browser
- **GIVEN** a person is on a project's triage queue
- **WHEN** they activate Assets
- **THEN** the asset browser for the same project SHALL open
- **AND** the previous triage filters SHALL NOT be applied to the browser

#### Scenario: Current work area is identified
- **WHEN** a project screen is displayed
- **THEN** its current Assets or Triage link SHALL be identified to assistive technology and visibly to the person

### Requirement: Asset surfaces remain reachable

On every asset surface, the application SHALL provide links to Overview, Model sheet, and 3D viewer for that same project and asset. It SHALL identify the current surface without relying on color alone.

#### Scenario: Move from sheet to viewer
- **GIVEN** the model sheet for an asset is open
- **WHEN** the person activates 3D viewer
- **THEN** the viewer for the same project and asset SHALL open

#### Scenario: Return from viewer to overview
- **GIVEN** the 3D viewer for an asset is open
- **WHEN** the person activates Overview
- **THEN** the asset overview SHALL open

#### Scenario: Current surface is identified
- **WHEN** any asset surface is displayed
- **THEN** its current surface link SHALL be identified to assistive technology and visibly to the person
