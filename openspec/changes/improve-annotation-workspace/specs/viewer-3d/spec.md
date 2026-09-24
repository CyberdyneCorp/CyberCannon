# Viewer 3D

## ADDED Requirements

### Requirement: Part-aware annotation navigation

The viewer SHALL list 3D annotations beside the model with their anchored part and state. Selecting a list item SHALL open its thread and restore its authored view when available. Orphaned annotations SHALL remain identifiable as orphaned.

#### Scenario: Open a note by part

- **WHEN** a reviewer selects a 3D annotation from the part-aware list
- **THEN** the annotation thread opens and the viewer applies the recorded camera and animation hints

#### Scenario: Orphaned part

- **WHEN** an annotation's part is absent from the current export
- **THEN** the list names the expected part and identifies the annotation as orphaned
