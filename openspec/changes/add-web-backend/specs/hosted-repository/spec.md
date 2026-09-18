# Spec Delta

## Purpose

Defines how a hosted service reads and writes a game repository it does not own —
a persistent working copy per project, kept fresh on a schedule and on notification,
read from a consistent revision with its staleness stated, written back as direct
commits attributed to the person who made the edit, and rebuildable from nothing
but the remote repository.

## ADDED Requirements

### Requirement: The working copy is the service's view of the source of truth

The service SHALL serve every answer about a project's specifications from a
persistent working copy of that project's repository, and SHALL treat the
repository as authoritative for all specification content. No specification
content SHALL exist only in the service's own storage, and an edit SHALL NOT be
considered applied until it exists in the repository.

#### Scenario: An edit not in the repository is not applied
- **GIVEN** an accepted edit whose commit could not be recorded in the repository
- **WHEN** the same content is read afterwards
- **THEN** the read SHALL return the pre-edit content
- **AND** the caller SHALL have been told the edit did not apply

#### Scenario: Repository content wins over service storage
- **GIVEN** the repository and the service's own storage disagree about a
  specification's content
- **WHEN** that specification is read
- **THEN** the repository's content SHALL be returned

### Requirement: The index is rebuildable and never authoritative

Every answer the service gives SHALL be derivable from the working copy alone. The
service SHALL provide an operation that discards the entire index and rebuilds it
from the working copy, and after that operation every lookup, listing, search and
read SHALL return the same results as before it.

#### Scenario: Dropping the index loses no answer
- **GIVEN** a project whose assets, requests, statuses and links have been read
  and recorded
- **WHEN** the index is dropped entirely and rebuilt from the working copy
- **THEN** every previously answerable lookup, listing, search and read SHALL
  return the same result as before

#### Scenario: No write reaches only the index
- **WHEN** any durable content is created or changed through the service
- **THEN** it SHALL be written to the repository
- **AND** it SHALL survive a full index rebuild

#### Scenario: Rebuild is an operation, not a side effect
- **WHEN** an ordinary read is served
- **THEN** it SHALL NOT trigger a full index rebuild

### Requirement: A project is unavailable until its working copy is ready

When a project is configured, the service SHALL obtain a working copy of its
repository before serving reads for that project, and SHALL report the project as
provisioning until the working copy is usable. When the working copy cannot be
obtained — an unreachable remote, a rejected credential, a missing branch — the
service SHALL report the project as unavailable with the reason, and SHALL NOT
serve empty or partial results as if the project had no assets.

#### Scenario: Provisioning is reported, not faked
- **GIVEN** a project whose working copy is still being obtained
- **WHEN** its assets are listed
- **THEN** the response SHALL report the project as not yet ready
- **AND** SHALL NOT report an empty asset list

#### Scenario: Rejected credential is reported with its reason
- **GIVEN** a project whose repository credential is rejected by the remote
- **WHEN** the project is read
- **THEN** the response SHALL report the project as unavailable naming the
  credential as the reason

### Requirement: The working copy refreshes on a schedule and on notification

The service SHALL refresh each project's working copy at a configured interval,
and SHALL additionally refresh it when the repository host notifies it of new
commits. A notification SHALL be authenticated before it is acted upon, an
unauthenticated notification SHALL be ignored, and a notification for an unknown
project or an uninteresting branch SHALL be accepted and discarded without error.

#### Scenario: Notification triggers a refresh
- **GIVEN** a new commit on a project's configured branch
- **WHEN** an authenticated notification for that project is received
- **THEN** the working copy SHALL be refreshed to include that commit

#### Scenario: Unauthenticated notification is ignored
- **WHEN** a notification arrives without a valid authentication of its origin
- **THEN** it SHALL be ignored
- **AND** no refresh SHALL occur

#### Scenario: Scheduled refresh covers a missed notification
- **GIVEN** a notification that was never delivered
- **WHEN** the configured interval elapses
- **THEN** the working copy SHALL be refreshed and include the missed commits

#### Scenario: A failed refresh keeps the last good revision
- **GIVEN** a working copy at a known revision
- **WHEN** a refresh fails because the remote is unreachable
- **THEN** reads SHALL continue to be served from the last good revision
- **AND** the project SHALL NOT be reported as unavailable

### Requirement: Every read states the revision it was served from and how stale it may be

A response containing specification content SHALL state the repository revision it
was produced from and when that revision was last confirmed against the remote.
When the last successful refresh is older than the configured interval, the
response SHALL additionally indicate that the content may be stale.

#### Scenario: Revision and confirmation time are stated
- **WHEN** specification content is read
- **THEN** the response SHALL name the revision it was produced from
- **AND** SHALL state when that revision was last confirmed against the remote

#### Scenario: Staleness is surfaced, not hidden
- **GIVEN** refreshes have been failing for longer than the configured interval
- **WHEN** specification content is read
- **THEN** the response SHALL indicate that the content may be stale

### Requirement: Reads are isolated from an in-progress refresh

A read SHALL be served entirely from one repository revision. A read SHALL NOT
observe a working copy in a partially updated state, SHALL NOT fail because a
refresh is in progress, and two reads within one logical operation SHALL be able
to be served from the same revision.

#### Scenario: No partial tree is ever observed
- **GIVEN** a refresh that is in progress
- **WHEN** a specification is read
- **THEN** the content returned SHALL correspond to exactly one revision

#### Scenario: A refresh does not fail a read
- **GIVEN** a refresh that is in progress
- **WHEN** any read is issued
- **THEN** it SHALL be served rather than refused

#### Scenario: Multi-file reads agree
- **GIVEN** a compiled briefing assembled from several specification files
- **WHEN** a refresh lands between two of those file reads
- **THEN** the briefing SHALL be produced from a single revision

### Requirement: Write-back is a direct commit on a configured branch

An accepted edit SHALL be written back as a commit on the project's configured
branch and pushed to the remote. One logical edit SHALL produce exactly one
commit, whose message states what changed and which asset it concerns. The service
SHALL NOT open a pull request, create a branch per edit, or leave an edit
committed locally but unpushed.

#### Scenario: One edit, one pushed commit
- **GIVEN** an accepted edit to one specification
- **WHEN** it is written back
- **THEN** the configured branch SHALL contain exactly one new commit for it
- **AND** that commit SHALL be present on the remote

#### Scenario: A local commit that cannot be pushed is not reported as applied
- **GIVEN** an edit committed to the working copy
- **WHEN** pushing it to the remote fails
- **THEN** the caller SHALL be told the edit did not apply
- **AND** the working copy SHALL be returned to the remote's state

#### Scenario: Commit message identifies the change
- **WHEN** an edit is written back
- **THEN** its commit message SHALL name the asset and describe what changed

### Requirement: Commits are authored by the acting person through the actors mapping

A write-back commit SHALL be authored by the git identity mapped from the acting
person's verified subject in the project's actors mapping. When the acting person
has no mapping to a git identity, the write SHALL be refused with a message naming
the missing mapping, and SHALL NOT be committed under a shared, generic or service
identity. A write performed by an agent on a person's behalf SHALL record both the
person and the agent.

#### Scenario: Commit author is the person who made the edit
- **GIVEN** an acting person mapped to a git identity
- **WHEN** their edit is written back
- **THEN** the commit's author SHALL be that git identity

#### Scenario: Unmapped person is refused, not substituted
- **GIVEN** an acting person with no entry in the actors mapping
- **WHEN** they attempt an edit
- **THEN** the edit SHALL be refused naming the missing mapping
- **AND** no commit SHALL be created

#### Scenario: Agent-performed write names both
- **GIVEN** an edit performed by an agent acting as a person
- **WHEN** it is written back
- **THEN** the commit SHALL be authored by that person
- **AND** the record SHALL also identify the agent that performed it

### Requirement: Concurrent edits conflict rather than overwrite

An edit SHALL be applied only when the content it was composed against is
unchanged. When the content has changed — through another person's edit or a
commit made outside the service — the edit SHALL be refused as conflicting, the
current content and revision SHALL be reported, and nothing SHALL be written.

#### Scenario: Second writer is refused
- **GIVEN** two people who read the same specification at the same revision
- **WHEN** the first writes successfully and the second submits an edit composed
  against the original revision
- **THEN** the second edit SHALL be refused as conflicting
- **AND** the first person's change SHALL remain intact

#### Scenario: An outside commit conflicts too
- **GIVEN** a specification changed by a commit pushed directly to the repository
- **WHEN** an edit composed before that commit is submitted
- **THEN** it SHALL be refused as conflicting

#### Scenario: Non-overlapping edits both succeed
- **GIVEN** two edits to different specifications composed at the same revision
- **WHEN** both are submitted
- **THEN** both SHALL be applied

#### Scenario: A rejected push does not silently retry into a conflict
- **GIVEN** a push rejected because the remote advanced
- **WHEN** the service re-evaluates the edit against the new remote state
- **THEN** it SHALL apply the edit only if its content is still unchanged
- **AND** SHALL otherwise refuse it as conflicting

### Requirement: A lost or diverged working copy is recoverable by re-obtaining it

When a project's working copy is missing, corrupted, or has diverged from the
remote's configured branch, the service SHALL restore it by obtaining a fresh copy
from the remote, and SHALL resume serving that project without loss of any content
that exists in the repository. Local state that is not present in the remote SHALL
be discarded rather than preserved, and the service SHALL report that a recovery
occurred.

#### Scenario: Deleted working copy recovers
- **GIVEN** a project whose working copy has been deleted from the service's storage
- **WHEN** the project is next read
- **THEN** the working copy SHALL be restored from the remote
- **AND** every specification present in the repository SHALL be readable again

#### Scenario: Divergence resolves toward the remote
- **GIVEN** a working copy carrying local commits absent from the remote branch
- **WHEN** recovery runs
- **THEN** the working copy SHALL be reset to the remote branch
- **AND** the discarded local commits SHALL be reported

#### Scenario: Recovery does not resurrect refused edits
- **GIVEN** an edit that was refused because it could not be pushed
- **WHEN** the working copy is recovered
- **THEN** that edit SHALL NOT appear in the restored content
