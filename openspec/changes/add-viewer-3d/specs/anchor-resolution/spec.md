# Spec Delta

## Purpose

Resolves a stored 3D anchor against a loaded mesh so that feedback survives
re-export: the named part is the identity, the recorded point and normal are
re-projected hints, the saved camera restores the angle, and a part that no longer
exists produces an orphan rather than a plausible-looking lie.

## ADDED Requirements

### Requirement: The named part is the durable key; geometry is a hint

Resolution of a 3D anchor SHALL be determined by the anchor's named part, and
optionally its named bone. The recorded point and normal SHALL be treated as
positioning hints only and SHALL NOT participate in deciding whether the anchor
resolves. The system SHALL NOT store or resolve an anchor by triangle index,
barycentric coordinate, vertex index, or any other identifier that depends on the
mesh's topology.

#### Scenario: Retopology preserves the anchor
- **GIVEN** an annotation anchored to part `SM_MechScout_Shoulder_L`
- **WHEN** the mesh is retopologised with an entirely different triangle layout and
  that part still present
- **THEN** the annotation SHALL resolve to that part

#### Scenario: Topology identifiers are not stored
- **WHEN** a 3D anchor is created and written
- **THEN** the written anchor SHALL contain no triangle index, barycentric
  coordinate or vertex index

#### Scenario: A moved hint does not break resolution
- **GIVEN** an annotation whose recorded point now lies well away from the mesh
  surface, with its named part still present
- **WHEN** the anchor is resolved
- **THEN** it SHALL resolve to that part rather than being reported as orphaned

### Requirement: Hints are re-projected onto the named part's surface

When an anchor's named part is present, the system SHALL place the annotation at
the point on **that part's** surface nearest to the recorded hint point. The
placement SHALL be confined to the named part and SHALL NOT land on any other
part, even when another part's surface is nearer to the hint. The displayed normal
SHALL be taken from the surface at the re-projected point.

#### Scenario: Hint lands on the named part, not the nearest surface
- **GIVEN** an anchor on part `SM_MechScout_Shoulder_L` whose hint point is nearer
  to a surface of `SM_MechScout_Torso`
- **WHEN** the anchor is resolved
- **THEN** the annotation SHALL be placed on a surface of `SM_MechScout_Shoulder_L`

#### Scenario: Resolution does not depend on the camera
- **GIVEN** a resolved anchor
- **WHEN** the same anchor is resolved again from a different viewing direction
- **THEN** the resulting surface position SHALL be identical

### Requirement: Re-projection distance is surfaced when it is large

The system SHALL compare the re-projected position with the recorded hint point
and, when the distance between them exceeds a configured proportion of the named
part's bounding size, SHALL mark the annotation as possibly displaced and state
the distance. Such an annotation SHALL still resolve and remain visible; the
system SHALL NOT silently present a substantially moved annotation as unchanged.

#### Scenario: Large displacement is flagged
- **GIVEN** an anchor whose re-projected position is far from its recorded hint
  relative to the part's size
- **WHEN** the anchor is resolved
- **THEN** the annotation SHALL be shown as possibly displaced, stating the distance

#### Scenario: Small displacement is not flagged
- **GIVEN** an anchor whose re-projected position is within the configured
  proportion of the part's size
- **WHEN** the anchor is resolved
- **THEN** the annotation SHALL be shown without a displacement warning

### Requirement: A missing part yields an explicit orphan

When an anchor's named part is not present in the loaded mesh, the system SHALL
report the annotation as orphaned, naming the part it expected. It SHALL NOT place
the annotation on any other part, SHALL NOT place it at the recorded point in
space as if it were resolved, and SHALL NOT hide or delete it. Orphaned
annotations SHALL be listed and countable so a reviewer can find them without
inspecting each one.

#### Scenario: Renamed part orphans rather than relocates
- **GIVEN** an annotation anchored to part `SM_MechScout_Shoulder_L`
- **WHEN** an export is loaded in which that part is named `SM_MechScout_Pauldron_L`
- **THEN** the annotation SHALL be reported as orphaned, naming
  `SM_MechScout_Shoulder_L`
- **AND** it SHALL NOT be placed on `SM_MechScout_Pauldron_L`

#### Scenario: Orphans are listed
- **GIVEN** a loaded mesh for which three annotations are orphaned
- **WHEN** the asset's annotations are presented
- **THEN** the three SHALL be presented as orphaned and SHALL be countable as such

#### Scenario: Orphan status is determinable without rendering
- **GIVEN** the set of part names recorded for an export
- **WHEN** an asset's annotations are evaluated against that set
- **THEN** each annotation's orphan status SHALL be determinable from the part
  names alone, with no mesh geometry loaded

### Requirement: A missing bone narrows to the part rather than orphaning

When an anchor records a bone and the named part is present but the named bone is
not, the system SHALL resolve the anchor to the part, mark it as partially
resolved, and state that the recorded bone was not found. When both the part and
the bone are present, the anchor SHALL be reported as fully resolved.

#### Scenario: Bone absent, part present
- **GIVEN** an anchor naming part `SM_MechScout_Arm_L` and bone `bone_forearm_l`
- **WHEN** a mesh containing that part but no such bone is loaded
- **THEN** the anchor SHALL resolve to the part
- **AND** it SHALL be reported as partially resolved, naming the missing bone

#### Scenario: Part and bone both present
- **GIVEN** an anchor naming a part and a bone both present in the loaded mesh
- **WHEN** the anchor is resolved
- **THEN** it SHALL be reported as fully resolved

### Requirement: Opening an annotation restores its saved camera

When an annotation carrying a saved camera is opened, the viewer SHALL restore
that camera's position, target and field of view before presenting the
annotation, so the reviewer sees what the author saw. When an annotation carries
no saved camera, the viewer SHALL frame the anchor's part and state that no camera
was recorded. Restoring a camera SHALL NOT modify the annotation.

#### Scenario: Saved camera is restored
- **GIVEN** an annotation with a recorded camera position, target and field of view
- **WHEN** it is opened in the viewer
- **THEN** the view SHALL be set to that position, target and field of view

#### Scenario: No saved camera falls back to framing the part
- **GIVEN** an annotation with no recorded camera
- **WHEN** it is opened in the viewer
- **THEN** its part SHALL be framed
- **AND** the viewer SHALL state that no camera was recorded

#### Scenario: Restoring does not rewrite the annotation
- **GIVEN** an annotation with a recorded camera
- **WHEN** it is opened and the view is subsequently changed by the reader
- **THEN** the annotation's recorded camera SHALL be unchanged

### Requirement: Creating an anchor records the part under the pointer

When a new 3D annotation is placed by pointing at the mesh, the system SHALL
record the name of the part under the pointer as the anchor's durable key, the
surface position and normal as hints expressed in that part's own space, and the
current camera. A placement that does not land on any part SHALL NOT create an
anchor, and SHALL say so. A placement on a hidden or isolated-away part SHALL NOT
be recorded.

#### Scenario: Placement records the named part
- **GIVEN** a loaded mesh with a part named `SM_MechScout_Shoulder_L`
- **WHEN** an annotation is placed by pointing at that part
- **THEN** the anchor SHALL record `SM_MechScout_Shoulder_L` as its part
- **AND** it SHALL record the surface point, the normal and the current camera

#### Scenario: Placement on empty space is refused
- **WHEN** an annotation placement lands on no part
- **THEN** no anchor SHALL be created
- **AND** the viewer SHALL state that a part must be pointed at

### Requirement: An orphan can be re-anchored to a part by hand

The system SHALL allow a person to re-anchor an orphaned annotation by selecting a
part of the loaded mesh, recording the newly chosen part, a new hint point and
normal and the current camera. The re-anchored annotation SHALL cease to be
orphaned, SHALL retain its identifier, text, thread and open state, and the
re-anchoring SHALL be attributed to the person who performed it and, where an
automated caller was involved, to that caller as well. Re-anchoring SHALL NOT be
performed automatically and SHALL NOT be available to an automated caller acting
on its own.

#### Scenario: Re-anchoring clears the orphan state
- **GIVEN** an annotation orphaned because `SM_MechScout_Shoulder_L` is absent
- **WHEN** a person re-anchors it to `SM_MechScout_Pauldron_L`
- **THEN** the annotation SHALL resolve to `SM_MechScout_Pauldron_L`
- **AND** it SHALL no longer be reported as orphaned

#### Scenario: Re-anchoring preserves the conversation
- **GIVEN** an orphaned annotation with an identifier, text and replies
- **WHEN** it is re-anchored
- **THEN** its identifier, text, replies and open state SHALL be unchanged

#### Scenario: Re-anchoring is attributed
- **WHEN** a person re-anchors an annotation through an automated caller acting on
  their behalf
- **THEN** the recorded change SHALL name both that person and the caller

#### Scenario: Nothing re-anchors on its own
- **GIVEN** an orphaned annotation and a loaded mesh containing a plausible
  replacement part
- **WHEN** the mesh is loaded and resolved
- **THEN** the annotation SHALL remain orphaned until a person re-anchors it

### Requirement: Anchors resolve identically against preview and source

An anchor SHALL resolve to the same named part whether it is resolved against the
preview mesh or against the source export it was derived from. A part present in
the source but absent from the preview SHALL be reported as a preview limitation,
distinct from the part having been removed from the asset.

#### Scenario: Same part resolved in both
- **GIVEN** an anchor on a part present in both the source export and its preview
- **WHEN** the anchor is resolved against each
- **THEN** it SHALL resolve to the same named part in both cases

#### Scenario: Part dropped by preview emission is not an orphan
- **GIVEN** a part present in the source export but absent from its preview
- **WHEN** an anchor on that part is resolved against the preview
- **THEN** the system SHALL state that the part is missing from the preview
- **AND** it SHALL NOT report the part as removed from the asset
