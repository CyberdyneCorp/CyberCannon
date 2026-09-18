# Spec Delta

## Purpose

Plays the animation clips carried by an asset's preview and shows which declared
design state each clip satisfies, so motion, timing and a state with no clip at
all are all visible in the same place where feedback is written.

## ADDED Requirements

### Requirement: Clips present in the preview are listed by name

When a preview carrying animation clips is displayed, the viewer SHALL list those
clips by name with each clip's duration. When the preview carries no clips, the
viewer SHALL state that this preview carries no clips and SHALL NOT present a
transport control that cannot act.

#### Scenario: Clips are listed
- **GIVEN** a preview carrying clips `A_mech_scout_walk` and `A_mech_scout_fire`
- **WHEN** the asset is displayed
- **THEN** both clip names SHALL be listed with their durations

#### Scenario: A preview with no clips says so
- **GIVEN** a preview carrying no animation clips
- **WHEN** the asset is displayed
- **THEN** the viewer SHALL state that the preview carries no clips
- **AND** no playback transport SHALL be offered

### Requirement: A preview that lost its clips is distinguished from an asset with none

When an asset's export is recorded as carrying animation clips but the preview
displayed carries none, the viewer SHALL state that clips are unavailable for this
preview. It SHALL NOT state that the asset has no animation.

#### Scenario: Clips lost in preview emission
- **GIVEN** an export recorded as carrying `A_mech_scout_walk`
- **AND** a preview of that export carrying no clips
- **WHEN** the asset is displayed
- **THEN** the viewer SHALL state that clips are unavailable for this preview
- **AND** it SHALL NOT report the asset as having no animation

### Requirement: Playback transport

The viewer SHALL allow a listed clip to be selected and played, paused, resumed
and scrubbed to any position within its duration, SHALL allow looping to be turned
on and off, and SHALL allow playback speed to be changed among at least a slowed,
a normal and an accelerated setting. The current position SHALL be displayed while
playing and while paused. Selected clip, position, loop and speed are view state
and SHALL NOT be written to the specification.

#### Scenario: Pause holds the displayed pose
- **GIVEN** a clip playing
- **WHEN** playback is paused
- **THEN** the displayed pose SHALL remain at the paused position
- **AND** the current position SHALL be displayed

#### Scenario: Scrubbing is deterministic
- **GIVEN** a paused clip
- **WHEN** it is scrubbed to a given position twice from different starting points
- **THEN** the displayed pose SHALL be identical both times

#### Scenario: Speed does not alter the clip
- **GIVEN** a clip played at an accelerated speed
- **WHEN** its duration is displayed
- **THEN** the duration reported SHALL be the clip's own duration

#### Scenario: Playback leaves no trace in the specification
- **GIVEN** a clip has been played, scrubbed and looped
- **WHEN** the specification file is inspected
- **THEN** it SHALL be unchanged

### Requirement: Each clip states which declared design state it satisfies

The viewer SHALL show, for each listed clip, the declared design state that
requires it, using the required clip name already derivable from the
specification. A clip that no declared state requires SHALL be listed and labelled
as satisfying no declared state; this SHALL NOT be presented as an error. The
viewer SHALL NOT infer a state-to-clip association by similarity of names.

#### Scenario: Clip is attributed to its state
- **GIVEN** a declared state `fire` whose required clip is `A_mech_scout_fire`
- **AND** a preview carrying a clip of that name
- **WHEN** the clips are listed
- **THEN** that clip SHALL be shown as satisfying the state `fire`

#### Scenario: An unclaimed clip is labelled, not rejected
- **GIVEN** a preview carrying a clip `A_mech_scout_test` that no declared state
  requires
- **WHEN** the clips are listed
- **THEN** it SHALL be listed and labelled as satisfying no declared state

### Requirement: A declared state with no clip is visibly absent

The viewer SHALL list every declared design state that requires a clip, including
those for which no clip is present in the preview, and SHALL show such a state as
having no clip. A state explicitly declared as having no animation SHALL be shown
as such and SHALL NOT be presented as missing.

#### Scenario: Missing clip is shown, not omitted
- **GIVEN** declared states `walk` and `fire` requiring clips, with only `walk`'s
  clip present in the preview
- **WHEN** the clips are listed
- **THEN** `fire` SHALL be listed as having no clip
- **AND** it SHALL NOT be omitted from the listing

#### Scenario: A deliberately unanimated state is not a gap
- **GIVEN** a state `destroyed` declared as having no animation
- **WHEN** the clips are listed
- **THEN** it SHALL be shown as declared unanimated
- **AND** it SHALL NOT be shown as having a missing clip

### Requirement: Annotating a paused frame records the clip and position as hints

When an annotation is placed while a clip is selected, the anchor SHALL record the
clip name and the position within that clip, expressed as a proportion of the
clip's duration rather than as a frame index, together with the camera. These
SHALL be recorded as viewing hints alongside the point and normal, and SHALL NOT
form part of the anchor's durable key. The recorded point and normal SHALL be
expressed in the anchored part's own space, so that the pose displayed at the time
of authoring does not alter them.

#### Scenario: Clip and position are recorded
- **GIVEN** the clip `A_mech_scout_walk` paused at the middle of its duration
- **WHEN** an annotation is placed on a part
- **THEN** the anchor SHALL record the clip name and a position of one half
- **AND** it SHALL NOT record a frame index

#### Scenario: Pose does not corrupt the hint
- **GIVEN** the same part annotated at the same surface location, once in the rest
  pose and once during a clip that displaces that part
- **WHEN** both anchors are compared
- **THEN** their recorded point and normal SHALL be equivalent

#### Scenario: The durable key is unaffected
- **WHEN** an annotation is placed during playback
- **THEN** the anchor SHALL still resolve by its named part
- **AND** removing the clip from a later export SHALL NOT orphan it

### Requirement: Replaying an annotation restores its clip, position and camera

When an annotation carrying a clip hint is opened and that clip is present in the
displayed preview, the viewer SHALL select that clip, set it to the recorded
position, hold it paused there, and restore the recorded camera. When the recorded
clip is not present, the viewer SHALL open the annotation against the rest pose,
restore the camera, and state that the recorded clip is unavailable.

#### Scenario: Frame and camera are restored together
- **GIVEN** an annotation recorded at three quarters of `A_mech_scout_walk` with a
  camera
- **WHEN** it is opened and that clip is present
- **THEN** the clip SHALL be selected and held paused at three quarters
- **AND** the recorded camera SHALL be restored

#### Scenario: Missing clip degrades without breaking the annotation
- **GIVEN** an annotation recorded against a clip absent from the current preview
- **WHEN** it is opened
- **THEN** the annotation SHALL be shown on its part in the rest pose
- **AND** the viewer SHALL state that the recorded clip is unavailable

### Requirement: Playing does not move resolved annotations

While a clip plays, annotations resolved against the displayed mesh SHALL continue
to identify their named parts. The system SHALL NOT re-record an anchor's hint,
camera, clip or position as a consequence of playback, scrubbing or looping.

#### Scenario: Playback does not rewrite anchors
- **GIVEN** an asset with resolved annotations
- **WHEN** a clip is played through and looped
- **THEN** every annotation's recorded anchor SHALL be unchanged
