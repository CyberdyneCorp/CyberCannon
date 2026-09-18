# Spec Delta

## Purpose

Brings concept art into the canon: which images are accepted, which view slot each
one occupies, how an asset comes into existence from an upload, how the files land
in the repository committed to the person who uploaded them, how blob storage and
thumbnails derive from that commit, and why a failed upload leaves no trace.

## ADDED Requirements

### Requirement: Accepted image formats

The system SHALL accept an uploaded concept view only in the formats declared
acceptable by the project configuration, whose default set is PNG, JPEG and WebP.
An image in any other format SHALL be rejected with a message naming the detected
format and the accepted set. Format SHALL be determined from the file's own
content, not from its filename extension.

#### Scenario: An unsupported format is rejected
- **GIVEN** a project whose accepted formats are PNG, JPEG and WebP
- **WHEN** a TIFF image is uploaded as a concept view
- **THEN** the upload SHALL be rejected with a message naming TIFF and the accepted set
- **AND** no file SHALL be written to the repository

#### Scenario: Content decides, not the extension
- **GIVEN** a TIFF image whose filename ends in `.png`
- **WHEN** it is uploaded
- **THEN** the upload SHALL be rejected as a TIFF

### Requirement: Size and dimension limits

The system SHALL reject an uploaded image whose byte size exceeds the project's
configured maximum, or whose width or height in pixels exceeds the project's
configured maximum dimension. Each rejection SHALL state the observed value and
the allowed value. An image at exactly the configured limit SHALL be accepted.

#### Scenario: Oversized file is rejected with numbers
- **GIVEN** a configured maximum of 25 MB per image
- **WHEN** a 41 MB image is uploaded
- **THEN** the upload SHALL be rejected stating observed 41 MB and allowed 25 MB

#### Scenario: Oversized dimensions are rejected
- **GIVEN** a configured maximum dimension of 8192 pixels
- **WHEN** an image of 12000 by 4000 pixels is uploaded
- **THEN** the upload SHALL be rejected stating the observed width and the allowed maximum

#### Scenario: Exactly at the limit is accepted
- **GIVEN** a configured maximum dimension of 8192 pixels
- **WHEN** an image of 8192 by 8192 pixels within the size limit is uploaded
- **THEN** the upload SHALL be accepted

### Requirement: Every view occupies exactly one named slot

Each uploaded image SHALL be assigned to exactly one view slot on exactly one
asset, identified by a slot name supplied with the upload. The names `front`,
`side` and `back` SHALL be recognised as canonical slots; any other name composed
of lowercase letters, digits and underscores, beginning with a letter or digit and
at most 32 characters long, SHALL be accepted as an arbitrary named view. An
upload without a slot name, or with a name that does not satisfy that rule, SHALL
be rejected naming the offending value.

#### Scenario: Canonical slot
- **WHEN** an image is uploaded to the slot `front` of an asset
- **THEN** it SHALL become that asset's `front` view

#### Scenario: Arbitrary named view
- **WHEN** an image is uploaded to the slot `three_quarter_left`
- **THEN** it SHALL be accepted as a named view of that asset

#### Scenario: Invalid slot name
- **WHEN** an image is uploaded to the slot `Front View!`
- **THEN** the upload SHALL be rejected naming that value as an invalid slot name

#### Scenario: A slot holds one view
- **GIVEN** an asset whose `front` slot already holds a view
- **WHEN** another image is uploaded to `front`
- **THEN** the existing view SHALL be replaced rather than a second `front` view created
- **AND** the replacement SHALL be recorded as a new revision of that view

### Requirement: An upload may create the asset it targets

When an upload names an asset identifier for which no specification exists, the
system SHALL create a minimal valid specification for it carrying its identifier,
its name and the status `concept`, and SHALL commit that specification together
with the uploaded view. The created specification SHALL NOT contain `design` or
`constraints` fields, empty or otherwise. When the asset already exists, ingestion
SHALL NOT modify any authored field of its specification.

#### Scenario: Creating an asset by uploading its first concept
- **GIVEN** no specification exists for `mech_scout`
- **WHEN** an image is uploaded to the `front` slot of `mech_scout`
- **THEN** a specification for `mech_scout` SHALL be created with status `concept`
- **AND** it SHALL contain no `design` or `constraints` fields
- **AND** the specification and the image SHALL appear in the same commit

#### Scenario: Existing authored content is untouched
- **GIVEN** an asset whose specification declares a triangle budget and two sockets
- **WHEN** a new concept view is uploaded to it
- **THEN** the triangle budget and sockets SHALL be unchanged in the resulting specification

#### Scenario: An invalid asset identifier creates nothing
- **WHEN** an upload names an asset identifier that does not satisfy the identifier rule
- **THEN** the upload SHALL be rejected naming the identifier
- **AND** no specification SHALL be created

### Requirement: Ingestion does not change an asset's status

Uploading, replacing or removing a concept view SHALL NOT change the asset's
`status`. A status change SHALL remain a separate, explicit human action.

#### Scenario: A late concept view does not demote an asset
- **GIVEN** an asset at status `validated`
- **WHEN** a new concept view is uploaded to it
- **THEN** its status SHALL still be `validated`

#### Scenario: A first view does not promote an asset
- **GIVEN** an asset created by its first upload at status `concept`
- **WHEN** two further views are uploaded
- **THEN** its status SHALL still be `concept`

### Requirement: Views are committed to the repository attributed to the uploader

A successfully ingested view SHALL be written into the project's repository
working copy at a path determined by the asset and the slot name, and committed to
the project's configured branch. The commit's author SHALL be the git identity of
the acting person, resolved from the identity mapping. The acting person SHALL be
determined from the credential the request was made with and SHALL NOT be taken
from any request parameter. When the upload was made through an agent on a
person's behalf, the commit SHALL record both the person and the agent. The commit
message SHALL name the asset and every slot written.

#### Scenario: Commit authorship is the uploader
- **GIVEN** an artist whose identity maps to a git author
- **WHEN** she uploads a concept view
- **THEN** the resulting commit's author SHALL be that git author

#### Scenario: A supplied author is ignored
- **GIVEN** an upload request that also carries an author field naming another person
- **WHEN** it is ingested
- **THEN** the commit SHALL be attributed to the person the credential identifies
- **AND** the supplied author field SHALL have no effect on attribution

#### Scenario: Agent-mediated upload names both
- **GIVEN** an agent acting for a person
- **WHEN** it ingests a view on that person's behalf
- **THEN** the recorded attribution SHALL name the person and the agent

#### Scenario: An unmappable person is refused before any write
- **GIVEN** an acting person with no entry in the identity mapping
- **WHEN** an upload is attempted
- **THEN** it SHALL be refused with a message naming the missing mapping
- **AND** no file SHALL be written and no blob object SHALL be retained

### Requirement: The repository is the source of truth; blob storage is a mirror

After a view is committed, the system SHALL mirror the image to blob storage keyed
by its content hash. The mirror SHALL be reconstructible in full from the
repository alone: deleting every mirrored object and every thumbnail and rebuilding
SHALL restore every view. No view SHALL exist in blob storage without existing in
the repository. Mirroring SHALL NOT be a precondition for a view being valid: when
blob storage is unavailable or not configured, the commit SHALL still succeed and
the view SHALL be reported as awaiting mirroring.

#### Scenario: Rebuilding the mirror from the repository
- **GIVEN** a project with twelve concept views and a populated blob store
- **WHEN** every mirrored object and thumbnail is deleted and a rebuild is run
- **THEN** all twelve views SHALL be available again with the same content hashes

#### Scenario: Mirror outage does not block ingestion
- **GIVEN** blob storage is unreachable
- **WHEN** a concept view is uploaded
- **THEN** the view SHALL be committed to the repository
- **AND** it SHALL be reported as awaiting mirroring rather than as failed

#### Scenario: No blob storage configured at all
- **GIVEN** a project configured with no blob storage
- **WHEN** a concept view is uploaded
- **THEN** the view SHALL be committed and readable from the repository

### Requirement: Thumbnails are derived, never authored

Thumbnails SHALL be derived from a committed view's image and SHALL NOT be written
into the repository. Derivation SHALL be deterministic: deriving twice from the
same source image SHALL produce thumbnails with the same content hash. Deleting
every thumbnail SHALL be recoverable by re-deriving from the repository, and a
thumbnail SHALL never be the only copy of anything.

#### Scenario: Thumbnails stay out of the repository
- **WHEN** a concept view is ingested
- **THEN** no thumbnail file SHALL appear in the repository working copy or in the commit

#### Scenario: Deterministic derivation
- **WHEN** thumbnails are derived twice from the same committed image
- **THEN** both derivations SHALL produce the same content hashes

#### Scenario: Thumbnails are recoverable
- **GIVEN** every thumbnail has been deleted
- **WHEN** derivation is run again over the project
- **THEN** every view SHALL have its thumbnails again with no upload required

### Requirement: A multi-image upload is all or nothing

An ingestion request carrying several images SHALL validate every image and every
slot name before writing anything, and SHALL produce a single commit containing
all of them. If any image in the request is rejected for any reason, the whole
request SHALL be rejected, naming each offending image and its reason, and no
commit SHALL be produced.

#### Scenario: Three views, one commit
- **WHEN** a request uploads images to `front`, `side` and `back` of one asset
- **THEN** exactly one commit SHALL be produced containing all three files

#### Scenario: One bad image rejects the request
- **GIVEN** a request carrying three images of which one exceeds the size limit
- **WHEN** it is ingested
- **THEN** the request SHALL be rejected naming the oversized image and its size
- **AND** no commit SHALL be produced and none of the three views SHALL exist

#### Scenario: Two images cannot claim the same slot
- **WHEN** a request uploads two images both naming the slot `side` of one asset
- **THEN** the request SHALL be rejected naming the conflicting slot
- **AND** no commit SHALL be produced

### Requirement: A failed ingestion leaves neither a partial commit nor an orphan blob

When ingestion fails at any point, the system SHALL leave every path it would have
written either absent or byte-identical to its prior content, SHALL leave no commit
that contains part of the request, and SHALL retain no blob object written for that
request. Once the commit has succeeded, the view SHALL be considered ingested: a
subsequent mirroring or thumbnail failure SHALL be reported as a pending derived
step and SHALL NOT be reported as a failed upload.

#### Scenario: Failure while writing leaves the working copy as it was
- **GIVEN** an ingestion request that fails while writing its files
- **WHEN** the repository working copy is examined
- **THEN** every path the request would have written SHALL be absent or unchanged
- **AND** no commit from that request SHALL exist

#### Scenario: Failure before commit retains no blob object
- **GIVEN** an ingestion request that fails before its commit succeeds
- **WHEN** blob storage is examined
- **THEN** no object written for that request SHALL remain

#### Scenario: Post-commit derived failure is a pending step, not a failed upload
- **GIVEN** a request whose commit succeeded and whose thumbnail derivation then failed
- **WHEN** the result is reported
- **THEN** the view SHALL be reported as ingested with thumbnail derivation pending

### Requirement: Ingestion never consults a language or vision model

Ingestion SHALL complete normally with model access disabled, misconfigured or
unreachable, and SHALL NOT produce descriptions, tags or suggested aliases as a
consequence of an upload. Generated content for an ingested view SHALL be produced
only by the separate `derived-metadata` capability, invoked explicitly after the
view exists.

#### Scenario: Ingestion with model access disabled
- **GIVEN** model access is disabled
- **WHEN** a concept view is uploaded
- **THEN** ingestion SHALL succeed and the view SHALL be committed and mirrored

#### Scenario: Uploading generates nothing
- **WHEN** a concept view is ingested
- **THEN** no description, tag or suggested alias SHALL be produced by that action
- **AND** the asset's specification SHALL contain nothing that was not uploaded or authored

### Requirement: A replaced view becomes visible without a manual reload

When a view's image is replaced in the repository, a surface already presenting
that view SHALL either present the new revision within a bounded interval stated by
the project configuration, or present the view marked as stale. A superseded image
SHALL NOT be presented as current. A view's presented identity SHALL include the
content hash of the revision being shown, so that a cached image can be recognised
as superseded.

#### Scenario: A newly exported render appears
- **GIVEN** a person viewing the `front` view of an asset
- **WHEN** a new export replaces that view's file in the repository
- **THEN** within the configured interval that person SHALL be shown the new revision, or the view SHALL be marked stale
- **AND** in neither case SHALL the superseded image be labelled current

#### Scenario: Freshness cannot be established
- **GIVEN** a surface that cannot determine whether the view it shows is current
- **WHEN** it presents the view
- **THEN** it SHALL mark the view as stale rather than assert that it is current

#### Scenario: Cached images are distinguishable by content
- **GIVEN** two revisions of one view with different content hashes
- **WHEN** either is presented
- **THEN** the presented identity SHALL include the content hash of the revision shown
