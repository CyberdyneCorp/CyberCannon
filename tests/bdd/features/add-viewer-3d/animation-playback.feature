# Generated from openspec/changes/add-viewer-3d/specs/animation-playback/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-viewer-3d @capability:animation-playback @spec:openspec/changes/add-viewer-3d/specs/animation-playback/spec.md
Feature: animation-playback

  Rule: Clips present in the preview are listed by name

    Scenario: Clips are listed
      Given a preview carrying clips `A_mech_scout_walk` and `A_mech_scout_fire`
      When the asset is displayed
      Then both clip names SHALL be listed with their durations

    Scenario: A preview with no clips says so
      Given a preview carrying no animation clips
      When the asset is displayed
      Then the viewer SHALL state that the preview carries no clips
      And no playback transport SHALL be offered

  Rule: A preview that lost its clips is distinguished from an asset with none

    Scenario: Clips lost in preview emission
      Given an export recorded as carrying `A_mech_scout_walk`
      And a preview of that export carrying no clips
      When the asset is displayed
      Then the viewer SHALL state that clips are unavailable for this preview
      And it SHALL NOT report the asset as having no animation

  Rule: Playback transport

    Scenario: Pause holds the displayed pose
      Given a clip playing
      When playback is paused
      Then the displayed pose SHALL remain at the paused position
      And the current position SHALL be displayed

    Scenario: Scrubbing is deterministic
      Given a paused clip
      When it is scrubbed to a given position twice from different starting points
      Then the displayed pose SHALL be identical both times

    Scenario: Speed does not alter the clip
      Given a clip played at an accelerated speed
      When its duration is displayed
      Then the duration reported SHALL be the clip's own duration

    Scenario: Playback leaves no trace in the specification
      Given a clip has been played, scrubbed and looped
      When the specification file is inspected
      Then it SHALL be unchanged

  Rule: Each clip states which declared design state it satisfies

    Scenario: Clip is attributed to its state
      Given a declared state `fire` whose required clip is `A_mech_scout_fire`
      And a preview carrying a clip of that name
      When the clips are listed
      Then that clip SHALL be shown as satisfying the state `fire`

    Scenario: An unclaimed clip is labelled, not rejected
      Given a preview carrying a clip `A_mech_scout_test` that no declared state requires
      When the clips are listed
      Then it SHALL be listed and labelled as satisfying no declared state

  Rule: A declared state with no clip is visibly absent

    Scenario: Missing clip is shown, not omitted
      Given declared states `walk` and `fire` requiring clips, with only `walk`'s clip present in the preview
      When the clips are listed
      Then `fire` SHALL be listed as having no clip
      And it SHALL NOT be omitted from the listing

    Scenario: A deliberately unanimated state is not a gap
      Given a state `destroyed` declared as having no animation
      When the clips are listed
      Then it SHALL be shown as declared unanimated
      And it SHALL NOT be shown as having a missing clip

  Rule: Annotating a paused frame records the clip and position as hints

    Scenario: Clip and position are recorded
      Given the clip `A_mech_scout_walk` paused at the middle of its duration
      When an annotation is placed on a part
      Then the anchor SHALL record the clip name and a position of one half
      And it SHALL NOT record a frame index

    Scenario: Pose does not corrupt the hint
      Given the same part annotated at the same surface location, once in the rest pose and once during a clip that displaces that part
      When both anchors are compared
      Then their recorded point and normal SHALL be equivalent

    Scenario: The durable key is unaffected
      When an annotation is placed during playback
      Then the anchor SHALL still resolve by its named part
      And removing the clip from a later export SHALL NOT orphan it

  Rule: Replaying an annotation restores its clip, position and camera

    Scenario: Frame and camera are restored together
      Given an annotation recorded at three quarters of `A_mech_scout_walk` with a camera
      When it is opened and that clip is present
      Then the clip SHALL be selected and held paused at three quarters
      And the recorded camera SHALL be restored

    Scenario: Missing clip degrades without breaking the annotation
      Given an annotation recorded against a clip absent from the current preview
      When it is opened
      Then the annotation SHALL be shown on its part in the rest pose
      And the viewer SHALL state that the recorded clip is unavailable

  Rule: Playing does not move resolved annotations

    Scenario: Playback does not rewrite anchors
      Given an asset with resolved annotations
      When a clip is played through and looped
      Then every annotation's recorded anchor SHALL be unchanged
