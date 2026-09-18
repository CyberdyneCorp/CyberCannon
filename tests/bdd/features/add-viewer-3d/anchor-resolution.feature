# Generated from openspec/changes/add-viewer-3d/specs/anchor-resolution/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-viewer-3d @capability:anchor-resolution @spec:openspec/changes/add-viewer-3d/specs/anchor-resolution/spec.md
Feature: anchor-resolution

  Rule: The named part is the durable key; geometry is a hint

    Scenario: Retopology preserves the anchor
      Given an annotation anchored to part `SM_MechScout_Shoulder_L`
      When the mesh is retopologised with an entirely different triangle layout and that part still present
      Then the annotation SHALL resolve to that part

    Scenario: Topology identifiers are not stored
      When a 3D anchor is created and written
      Then the written anchor SHALL contain no triangle index, barycentric coordinate or vertex index

    Scenario: A moved hint does not break resolution
      Given an annotation whose recorded point now lies well away from the mesh surface, with its named part still present
      When the anchor is resolved
      Then it SHALL resolve to that part rather than being reported as orphaned

  Rule: Hints are re-projected onto the named part's surface

    Scenario: Hint lands on the named part, not the nearest surface
      Given an anchor on part `SM_MechScout_Shoulder_L` whose hint point is nearer to a surface of `SM_MechScout_Torso`
      When the anchor is resolved
      Then the annotation SHALL be placed on a surface of `SM_MechScout_Shoulder_L`

    Scenario: Resolution does not depend on the camera
      Given a resolved anchor
      When the same anchor is resolved again from a different viewing direction
      Then the resulting surface position SHALL be identical

  Rule: Re-projection distance is surfaced when it is large

    Scenario: Large displacement is flagged
      Given an anchor whose re-projected position is far from its recorded hint relative to the part's size
      When the anchor is resolved
      Then the annotation SHALL be shown as possibly displaced, stating the distance

    Scenario: Small displacement is not flagged
      Given an anchor whose re-projected position is within the configured proportion of the part's size
      When the anchor is resolved
      Then the annotation SHALL be shown without a displacement warning

  Rule: A missing part yields an explicit orphan

    Scenario: Renamed part orphans rather than relocates
      Given an annotation anchored to part `SM_MechScout_Shoulder_L`
      When an export is loaded in which that part is named `SM_MechScout_Pauldron_L`
      Then the annotation SHALL be reported as orphaned, naming `SM_MechScout_Shoulder_L`
      And it SHALL NOT be placed on `SM_MechScout_Pauldron_L`

    Scenario: Orphans are listed
      Given a loaded mesh for which three annotations are orphaned
      When the asset's annotations are presented
      Then the three SHALL be presented as orphaned and SHALL be countable as such

    Scenario: Orphan status is determinable without rendering
      Given the set of part names recorded for an export
      When an asset's annotations are evaluated against that set
      Then each annotation's orphan status SHALL be determinable from the part names alone, with no mesh geometry loaded

  Rule: A missing bone narrows to the part rather than orphaning

    Scenario: Bone absent, part present
      Given an anchor naming part `SM_MechScout_Arm_L` and bone `bone_forearm_l`
      When a mesh containing that part but no such bone is loaded
      Then the anchor SHALL resolve to the part
      And it SHALL be reported as partially resolved, naming the missing bone

    Scenario: Part and bone both present
      Given an anchor naming a part and a bone both present in the loaded mesh
      When the anchor is resolved
      Then it SHALL be reported as fully resolved

  Rule: Opening an annotation restores its saved camera

    Scenario: Saved camera is restored
      Given an annotation with a recorded camera position, target and field of view
      When it is opened in the viewer
      Then the view SHALL be set to that position, target and field of view

    Scenario: No saved camera falls back to framing the part
      Given an annotation with no recorded camera
      When it is opened in the viewer
      Then its part SHALL be framed
      And the viewer SHALL state that no camera was recorded

    Scenario: Restoring does not rewrite the annotation
      Given an annotation with a recorded camera
      When it is opened and the view is subsequently changed by the reader
      Then the annotation's recorded camera SHALL be unchanged

  Rule: Creating an anchor records the part under the pointer

    Scenario: Placement records the named part
      Given a loaded mesh with a part named `SM_MechScout_Shoulder_L`
      When an annotation is placed by pointing at that part
      Then the anchor SHALL record `SM_MechScout_Shoulder_L` as its part
      And it SHALL record the surface point, the normal and the current camera

    Scenario: Placement on empty space is refused
      When an annotation placement lands on no part
      Then no anchor SHALL be created
      And the viewer SHALL state that a part must be pointed at

  Rule: An orphan can be re-anchored to a part by hand

    Scenario: Re-anchoring clears the orphan state
      Given an annotation orphaned because `SM_MechScout_Shoulder_L` is absent
      When a person re-anchors it to `SM_MechScout_Pauldron_L`
      Then the annotation SHALL resolve to `SM_MechScout_Pauldron_L`
      And it SHALL no longer be reported as orphaned

    Scenario: Re-anchoring preserves the conversation
      Given an orphaned annotation with an identifier, text and replies
      When it is re-anchored
      Then its identifier, text, replies and open state SHALL be unchanged

    Scenario: Re-anchoring is attributed
      When a person re-anchors an annotation through an automated caller acting on their behalf
      Then the recorded change SHALL name both that person and the caller

    Scenario: Nothing re-anchors on its own
      Given an orphaned annotation and a loaded mesh containing a plausible replacement part
      When the mesh is loaded and resolved
      Then the annotation SHALL remain orphaned until a person re-anchors it

  Rule: Anchors resolve identically against preview and source

    Scenario: Same part resolved in both
      Given an anchor on a part present in both the source export and its preview
      When the anchor is resolved against each
      Then it SHALL resolve to the same named part in both cases

    Scenario: Part dropped by preview emission is not an orphan
      Given a part present in the source export but absent from its preview
      When an anchor on that part is resolved against the preview
      Then the system SHALL state that the part is missing from the preview
      And it SHALL NOT report the part as removed from the asset
