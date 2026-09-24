# Asset workspace layout

## ADDED Requirements

### Requirement: Responsive asset inspection workspace

The asset viewer SHALL use available desktop width for the model while presenting parts and animation alongside it. At narrow widths, the same information and controls SHALL remain reachable in reading order.

#### Scenario: Wide asset viewer

- **WHEN** a reviewer opens a 3D asset viewer on a wide screen
- **THEN** the model viewport expands into the main column, and parts and animation appear in an adjacent tool column

#### Scenario: Narrow asset viewer

- **WHEN** a reviewer opens the viewer on a narrow screen
- **THEN** model, tools, and annotations form one readable column with no horizontal page overflow

### Requirement: Compact asset facts and discussions

The asset page SHALL use available width to place short overview sections and viewer discussions side by side where space allows, without hiding facts, threads, or actions.

#### Scenario: Wide asset overview

- **WHEN** a reviewer opens an asset overview on a wide screen
- **THEN** its fact sections occupy a responsive multi-column grid

#### Scenario: Viewer discussion

- **WHEN** a reviewer opens a thread in the wide viewer
- **THEN** the thread list and selected discussion remain visible in adjacent regions
