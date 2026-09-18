# Generated from openspec/changes/add-web-backend/specs/blob-storage/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-backend @capability:blob-storage @spec:openspec/changes/add-web-backend/specs/blob-storage/spec.md
Feature: blob-storage

  Rule: Blobs are a mirror and the repository stays authoritative

    Scenario: Repository decides which blobs matter
      Given a blob present in the store whose source file has been removed from the repository
      When the asset's views are listed
      Then the removed view SHALL NOT be listed

    Scenario: Upload without a repository source is refused
      When content is submitted for storage that corresponds to no repository file and is not derivable from one
      Then it SHALL be refused

  Rule: Blob keys are derived from content

    Scenario: Identical content stores once
      Given the same image referenced by two assets
      When both are mirrored
      Then both SHALL resolve to the same key and one stored object

    Scenario: Changed content gets a new key
      Given a stored blob
      When its source file's bytes change
      Then the new content SHALL store under a different key
      And references to the old key SHALL continue to resolve to the old content until it is removed

    Scenario: Renaming does not change the key
      Given a mirrored file
      When the file is renamed in the repository with unchanged content
      Then its key SHALL be unchanged

  Rule: Mirroring is idempotent and never partially visible

    Scenario: Re-mirroring is a no-op
      Given content already stored under its key
      When it is mirrored again
      Then the operation SHALL succeed
      And the stored object SHALL be unchanged

    Scenario: Interrupted upload leaves nothing readable
      Given an upload interrupted before completion
      When its key is read
      Then the read SHALL report the object as absent
      And SHALL NOT return truncated content

  Rule: Total loss of the blob store is recoverable from the repository

    Scenario: Empty store rebuilds
      Given a project whose views and preview meshes are readable
      When the blob store is emptied and re-mirroring runs
      Then every previously readable view, export and preview mesh SHALL be readable again
      And each SHALL resolve under the key it had before

    Scenario: A missing blob is reported, not fabricated
      Given a blob absent from the store and not yet re-mirrored
      When it is requested
      Then the response SHALL report it as temporarily unavailable
      And SHALL NOT report the asset as having no such view

  Rule: Reads are granted through signed, time-limited, single-object links

    Scenario: Expired link is refused
      Given a link issued for a blob
      When it is used after its expiry
      Then access SHALL be refused

    Scenario: A link is scoped to one object
      Given a link issued for one blob
      When it is modified to address a different stored object
      Then access SHALL be refused

    Scenario: Authorization precedes issuance
      Given an actor not permitted to read an asset
      When a link to one of that asset's blobs is requested
      Then the request SHALL be refused
      And no link SHALL be issued

  Rule: Stored content is verified against its key on read

    Scenario: Corrupted object is not served as valid
      Given a stored object whose bytes no longer match its key's digest
      When it is read
      Then the service SHALL report it as corrupt
      And SHALL NOT serve the mismatched bytes as the asset's content

    Scenario: Corruption is repairable
      Given an object reported as corrupt
      When re-mirroring runs for its project
      Then the object SHALL be replaced by content matching its key
