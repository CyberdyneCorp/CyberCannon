# Generated from openspec/changes/add-web-backend/specs/hosted-repository/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-web-backend @capability:hosted-repository @spec:openspec/changes/add-web-backend/specs/hosted-repository/spec.md
Feature: hosted-repository

  Rule: The working copy is the service's view of the source of truth

    Scenario: An edit not in the repository is not applied
      Given an accepted edit whose commit could not be recorded in the repository
      When the same content is read afterwards
      Then the read SHALL return the pre-edit content
      And the caller SHALL have been told the edit did not apply

    Scenario: Repository content wins over service storage
      Given the repository and the service's own storage disagree about a specification's content
      When that specification is read
      Then the repository's content SHALL be returned

  Rule: The index is rebuildable and never authoritative

    Scenario: Dropping the index loses no answer
      Given a project whose assets, requests, statuses and links have been read and recorded
      When the index is dropped entirely and rebuilt from the working copy
      Then every previously answerable lookup, listing, search and read SHALL return the same result as before

    Scenario: No write reaches only the index
      When any durable content is created or changed through the service
      Then it SHALL be written to the repository
      And it SHALL survive a full index rebuild

    Scenario: Rebuild is an operation, not a side effect
      When an ordinary read is served
      Then it SHALL NOT trigger a full index rebuild

  Rule: A project is unavailable until its working copy is ready

    Scenario: Provisioning is reported, not faked
      Given a project whose working copy is still being obtained
      When its assets are listed
      Then the response SHALL report the project as not yet ready
      And SHALL NOT report an empty asset list

    Scenario: Rejected credential is reported with its reason
      Given a project whose repository credential is rejected by the remote
      When the project is read
      Then the response SHALL report the project as unavailable naming the credential as the reason

  Rule: The working copy refreshes on a schedule and on notification

    Scenario: Notification triggers a refresh
      Given a new commit on a project's configured branch
      When an authenticated notification for that project is received
      Then the working copy SHALL be refreshed to include that commit

    Scenario: Unauthenticated notification is ignored
      When a notification arrives without a valid authentication of its origin
      Then it SHALL be ignored
      And no refresh SHALL occur

    Scenario: Scheduled refresh covers a missed notification
      Given a notification that was never delivered
      When the configured interval elapses
      Then the working copy SHALL be refreshed and include the missed commits

    Scenario: A failed refresh keeps the last good revision
      Given a working copy at a known revision
      When a refresh fails because the remote is unreachable
      Then reads SHALL continue to be served from the last good revision
      And the project SHALL NOT be reported as unavailable

  Rule: Every read states the revision it was served from and how stale it may be

    Scenario: Revision and confirmation time are stated
      When specification content is read
      Then the response SHALL name the revision it was produced from
      And SHALL state when that revision was last confirmed against the remote

    Scenario: Staleness is surfaced, not hidden
      Given refreshes have been failing for longer than the configured interval
      When specification content is read
      Then the response SHALL indicate that the content may be stale

  Rule: Reads are isolated from an in-progress refresh

    Scenario: No partial tree is ever observed
      Given a refresh that is in progress
      When a specification is read
      Then the content returned SHALL correspond to exactly one revision

    Scenario: A refresh does not fail a read
      Given a refresh that is in progress
      When any read is issued
      Then it SHALL be served rather than refused

    Scenario: Multi-file reads agree
      Given a compiled briefing assembled from several specification files
      When a refresh lands between two of those file reads
      Then the briefing SHALL be produced from a single revision

  Rule: Write-back is a direct commit on a configured branch

    Scenario: One edit, one pushed commit
      Given an accepted edit to one specification
      When it is written back
      Then the configured branch SHALL contain exactly one new commit for it
      And that commit SHALL be present on the remote

    Scenario: A local commit that cannot be pushed is not reported as applied
      Given an edit committed to the working copy
      When pushing it to the remote fails
      Then the caller SHALL be told the edit did not apply
      And the working copy SHALL be returned to the remote's state

    Scenario: Commit message identifies the change
      When an edit is written back
      Then its commit message SHALL name the asset and describe what changed

  Rule: Commits are authored by the acting person through the actors mapping

    Scenario: Commit author is the person who made the edit
      Given an acting person mapped to a git identity
      When their edit is written back
      Then the commit's author SHALL be that git identity

    Scenario: Unmapped person is refused, not substituted
      Given an acting person with no entry in the actors mapping
      When they attempt an edit
      Then the edit SHALL be refused naming the missing mapping
      And no commit SHALL be created

    Scenario: Agent-performed write names both
      Given an edit performed by an agent acting as a person
      When it is written back
      Then the commit SHALL be authored by that person
      And the record SHALL also identify the agent that performed it

  Rule: Concurrent edits conflict rather than overwrite

    Scenario: Second writer is refused
      Given two people who read the same specification at the same revision
      When the first writes successfully and the second submits an edit composed against the original revision
      Then the second edit SHALL be refused as conflicting
      And the first person's change SHALL remain intact

    Scenario: An outside commit conflicts too
      Given a specification changed by a commit pushed directly to the repository
      When an edit composed before that commit is submitted
      Then it SHALL be refused as conflicting

    Scenario: Non-overlapping edits both succeed
      Given two edits to different specifications composed at the same revision
      When both are submitted
      Then both SHALL be applied

    Scenario: A rejected push does not silently retry into a conflict
      Given a push rejected because the remote advanced
      When the service re-evaluates the edit against the new remote state
      Then it SHALL apply the edit only if its content is still unchanged
      And SHALL otherwise refuse it as conflicting

  Rule: A lost or diverged working copy is recoverable by re-obtaining it

    Scenario: Deleted working copy recovers
      Given a project whose working copy has been deleted from the service's storage
      When the project is next read
      Then the working copy SHALL be restored from the remote
      And every specification present in the repository SHALL be readable again

    Scenario: Divergence resolves toward the remote
      Given a working copy carrying local commits absent from the remote branch
      When recovery runs
      Then the working copy SHALL be reset to the remote branch
      And the discarded local commits SHALL be reported

    Scenario: Recovery does not resurrect refused edits
      Given an edit that was refused because it could not be pushed
      When the working copy is recovered
      Then that edit SHALL NOT appear in the restored content
