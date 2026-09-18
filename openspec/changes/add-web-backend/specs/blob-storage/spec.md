# Spec Delta

## Purpose

Defines the binary mirror that lets a browser load a concept view or a preview
mesh without cloning a game repository — content-addressed, re-derivable, never
authoritative, and read only through short-lived links issued after the same
authorization decision that governs the asset itself.

## ADDED Requirements

### Requirement: Blobs are a mirror and the repository stays authoritative

Every stored blob SHALL correspond to content that exists in, or is reproducible
from, the project's repository. The service SHALL NOT accept a blob with no
repository-side source, SHALL NOT treat the blob store as the record of what an
asset's views or exports are, and SHALL determine that set from the repository.

#### Scenario: Repository decides which blobs matter
- **GIVEN** a blob present in the store whose source file has been removed from the
  repository
- **WHEN** the asset's views are listed
- **THEN** the removed view SHALL NOT be listed

#### Scenario: Upload without a repository source is refused
- **WHEN** content is submitted for storage that corresponds to no repository file
  and is not derivable from one
- **THEN** it SHALL be refused

### Requirement: Blob keys are derived from content

A blob's storage key SHALL be derived from a digest of its bytes, such that
identical content stores under an identical key and different content never
shares a key. The key SHALL NOT depend on the file name, the asset it belongs to,
the time of upload, or the order in which blobs were stored.

#### Scenario: Identical content stores once
- **GIVEN** the same image referenced by two assets
- **WHEN** both are mirrored
- **THEN** both SHALL resolve to the same key and one stored object

#### Scenario: Changed content gets a new key
- **GIVEN** a stored blob
- **WHEN** its source file's bytes change
- **THEN** the new content SHALL store under a different key
- **AND** references to the old key SHALL continue to resolve to the old content
  until it is removed

#### Scenario: Renaming does not change the key
- **GIVEN** a mirrored file
- **WHEN** the file is renamed in the repository with unchanged content
- **THEN** its key SHALL be unchanged

### Requirement: Mirroring is idempotent and never partially visible

Mirroring content that is already stored SHALL succeed without re-uploading it and
without changing its key. An upload that fails or is interrupted SHALL leave no
readable object at its key, so that a key either resolves to complete, correct
content or does not resolve at all.

#### Scenario: Re-mirroring is a no-op
- **GIVEN** content already stored under its key
- **WHEN** it is mirrored again
- **THEN** the operation SHALL succeed
- **AND** the stored object SHALL be unchanged

#### Scenario: Interrupted upload leaves nothing readable
- **GIVEN** an upload interrupted before completion
- **WHEN** its key is read
- **THEN** the read SHALL report the object as absent
- **AND** SHALL NOT return truncated content

### Requirement: Total loss of the blob store is recoverable from the repository

The service SHALL provide an operation that re-mirrors a project's blobs from its
working copy. After the blob store has been emptied and that operation has run,
every view, export and preview mesh that the repository describes SHALL be
readable again under the same keys, and no content SHALL have been lost.

#### Scenario: Empty store rebuilds
- **GIVEN** a project whose views and preview meshes are readable
- **WHEN** the blob store is emptied and re-mirroring runs
- **THEN** every previously readable view, export and preview mesh SHALL be
  readable again
- **AND** each SHALL resolve under the key it had before

#### Scenario: A missing blob is reported, not fabricated
- **GIVEN** a blob absent from the store and not yet re-mirrored
- **WHEN** it is requested
- **THEN** the response SHALL report it as temporarily unavailable
- **AND** SHALL NOT report the asset as having no such view

### Requirement: Reads are granted through signed, time-limited, single-object links

Access to a blob's bytes SHALL be granted by a link that expires after a bounded
configured period, that is valid for exactly one stored object, and that cannot be
altered into a link for another object. The link SHALL be issued only after the
authorization decision governing the owning asset has permitted the actor to read
it, and an expired link SHALL be refused.

#### Scenario: Expired link is refused
- **GIVEN** a link issued for a blob
- **WHEN** it is used after its expiry
- **THEN** access SHALL be refused

#### Scenario: A link is scoped to one object
- **GIVEN** a link issued for one blob
- **WHEN** it is modified to address a different stored object
- **THEN** access SHALL be refused

#### Scenario: Authorization precedes issuance
- **GIVEN** an actor not permitted to read an asset
- **WHEN** a link to one of that asset's blobs is requested
- **THEN** the request SHALL be refused
- **AND** no link SHALL be issued

### Requirement: Stored content is verified against its key on read

When a blob is served, the service SHALL be able to confirm that the stored bytes
match the digest its key encodes, and SHALL report corruption rather than serve
content that does not match. Corrupted content SHALL be re-mirrorable from the
repository by the recovery operation.

#### Scenario: Corrupted object is not served as valid
- **GIVEN** a stored object whose bytes no longer match its key's digest
- **WHEN** it is read
- **THEN** the service SHALL report it as corrupt
- **AND** SHALL NOT serve the mismatched bytes as the asset's content

#### Scenario: Corruption is repairable
- **GIVEN** an object reported as corrupt
- **WHEN** re-mirroring runs for its project
- **THEN** the object SHALL be replaced by content matching its key
