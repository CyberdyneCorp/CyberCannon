# Generated from openspec/changes/add-concept-ingestion/specs/concept-ingestion/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-concept-ingestion @capability:concept-ingestion @spec:openspec/changes/add-concept-ingestion/specs/concept-ingestion/spec.md
Feature: concept-ingestion

  Rule: Accepted image formats

    Scenario: An unsupported format is rejected
      Given a project whose accepted formats are PNG, JPEG and WebP
      When a TIFF image is uploaded as a concept view
      Then the upload SHALL be rejected with a message naming TIFF and the accepted set
      And no file SHALL be written to the repository

    Scenario: Content decides, not the extension
      Given a TIFF image whose filename ends in `.png`
      When it is uploaded
      Then the upload SHALL be rejected as a TIFF

  Rule: Size and dimension limits

    Scenario: Oversized file is rejected with numbers
      Given a configured maximum of 25 MB per image
      When a 41 MB image is uploaded
      Then the upload SHALL be rejected stating observed 41 MB and allowed 25 MB

    Scenario: Oversized dimensions are rejected
      Given a configured maximum dimension of 8192 pixels
      When an image of 12000 by 4000 pixels is uploaded
      Then the upload SHALL be rejected stating the observed width and the allowed maximum

    Scenario: Exactly at the limit is accepted
      Given a configured maximum dimension of 8192 pixels
      When an image of 8192 by 8192 pixels within the size limit is uploaded
      Then the upload SHALL be accepted

  Rule: Every view occupies exactly one named slot

    Scenario: Canonical slot
      When an image is uploaded to the slot `front` of an asset
      Then it SHALL become that asset's `front` view

    Scenario: Arbitrary named view
      When an image is uploaded to the slot `three_quarter_left`
      Then it SHALL be accepted as a named view of that asset

    Scenario: Invalid slot name
      When an image is uploaded to the slot `Front View!`
      Then the upload SHALL be rejected naming that value as an invalid slot name

    Scenario: A slot holds one view
      Given an asset whose `front` slot already holds a view
      When another image is uploaded to `front`
      Then the existing view SHALL be replaced rather than a second `front` view created
      And the replacement SHALL be recorded as a new revision of that view

  Rule: An upload may create the asset it targets

    Scenario: Creating an asset by uploading its first concept
      Given no specification exists for `mech_scout`
      When an image is uploaded to the `front` slot of `mech_scout`
      Then a specification for `mech_scout` SHALL be created with status `concept`
      And it SHALL contain no `design` or `constraints` fields
      And the specification and the image SHALL appear in the same commit

    Scenario: Existing authored content is untouched
      Given an asset whose specification declares a triangle budget and two sockets
      When a new concept view is uploaded to it
      Then the triangle budget and sockets SHALL be unchanged in the resulting specification

    Scenario: An invalid asset identifier creates nothing
      When an upload names an asset identifier that does not satisfy the identifier rule
      Then the upload SHALL be rejected naming the identifier
      And no specification SHALL be created

  Rule: Ingestion does not change an asset's status

    Scenario: A late concept view does not demote an asset
      Given an asset at status `validated`
      When a new concept view is uploaded to it
      Then its status SHALL still be `validated`

    Scenario: A first view does not promote an asset
      Given an asset created by its first upload at status `concept`
      When two further views are uploaded
      Then its status SHALL still be `concept`

  Rule: Views are committed to the repository attributed to the uploader

    Scenario: Commit authorship is the uploader
      Given an artist whose identity maps to a git author
      When she uploads a concept view
      Then the resulting commit's author SHALL be that git author

    Scenario: A supplied author is ignored
      Given an upload request that also carries an author field naming another person
      When it is ingested
      Then the commit SHALL be attributed to the person the credential identifies
      And the supplied author field SHALL have no effect on attribution

    Scenario: Agent-mediated upload names both
      Given an agent acting for a person
      When it ingests a view on that person's behalf
      Then the recorded attribution SHALL name the person and the agent

    Scenario: An unmappable person is refused before any write
      Given an acting person with no entry in the identity mapping
      When an upload is attempted
      Then it SHALL be refused with a message naming the missing mapping
      And no file SHALL be written and no blob object SHALL be retained

  Rule: The repository is the source of truth; blob storage is a mirror

    Scenario: Rebuilding the mirror from the repository
      Given a project with twelve concept views and a populated blob store
      When every mirrored object and thumbnail is deleted and a rebuild is run
      Then all twelve views SHALL be available again with the same content hashes

    Scenario: Mirror outage does not block ingestion
      Given blob storage is unreachable
      When a concept view is uploaded
      Then the view SHALL be committed to the repository
      And it SHALL be reported as awaiting mirroring rather than as failed

    Scenario: No blob storage configured at all
      Given a project configured with no blob storage
      When a concept view is uploaded
      Then the view SHALL be committed and readable from the repository

  Rule: Thumbnails are derived, never authored

    Scenario: Thumbnails stay out of the repository
      When a concept view is ingested
      Then no thumbnail file SHALL appear in the repository working copy or in the commit

    Scenario: Deterministic derivation
      When thumbnails are derived twice from the same committed image
      Then both derivations SHALL produce the same content hashes

    Scenario: Thumbnails are recoverable
      Given every thumbnail has been deleted
      When derivation is run again over the project
      Then every view SHALL have its thumbnails again with no upload required

  Rule: A multi-image upload is all or nothing

    Scenario: Three views, one commit
      When a request uploads images to `front`, `side` and `back` of one asset
      Then exactly one commit SHALL be produced containing all three files

    Scenario: One bad image rejects the request
      Given a request carrying three images of which one exceeds the size limit
      When it is ingested
      Then the request SHALL be rejected naming the oversized image and its size
      And no commit SHALL be produced and none of the three views SHALL exist

    Scenario: Two images cannot claim the same slot
      When a request uploads two images both naming the slot `side` of one asset
      Then the request SHALL be rejected naming the conflicting slot
      And no commit SHALL be produced

  Rule: A failed ingestion leaves neither a partial commit nor an orphan blob

    Scenario: Failure while writing leaves the working copy as it was
      Given an ingestion request that fails while writing its files
      When the repository working copy is examined
      Then every path the request would have written SHALL be absent or unchanged
      And no commit from that request SHALL exist

    Scenario: Failure before commit retains no blob object
      Given an ingestion request that fails before its commit succeeds
      When blob storage is examined
      Then no object written for that request SHALL remain

    Scenario: Post-commit derived failure is a pending step, not a failed upload
      Given a request whose commit succeeded and whose thumbnail derivation then failed
      When the result is reported
      Then the view SHALL be reported as ingested with thumbnail derivation pending

  Rule: Ingestion never consults a language or vision model

    Scenario: Ingestion with model access disabled
      Given model access is disabled
      When a concept view is uploaded
      Then ingestion SHALL succeed and the view SHALL be committed and mirrored

    Scenario: Uploading generates nothing
      When a concept view is ingested
      Then no description, tag or suggested alias SHALL be produced by that action
      And the asset's specification SHALL contain nothing that was not uploaded or authored

  Rule: A replaced view becomes visible without a manual reload

    Scenario: A newly exported render appears
      Given a person viewing the `front` view of an asset
      When a new export replaces that view's file in the repository
      Then within the configured interval that person SHALL be shown the new revision, or the view SHALL be marked stale
      And in neither case SHALL the superseded image be labelled current

    Scenario: Freshness cannot be established
      Given a surface that cannot determine whether the view it shows is current
      When it presents the view
      Then it SHALL mark the view as stale rather than assert that it is current

    Scenario: Cached images are distinguishable by content
      Given two revisions of one view with different content hashes
      When either is presented
      Then the presented identity SHALL include the content hash of the revision shown
