# Generated from openspec/changes/add-coolify-deployment/specs/deployment-operations/spec.md by scripts/gen_features.py.
# Do not edit: run `just gen-features`. A hand edit fails `just features`.

@change:add-coolify-deployment @capability:deployment-operations @spec:openspec/changes/add-coolify-deployment/specs/deployment-operations/spec.md
Feature: deployment-operations

  Rule: The hosted inventory is exactly the networked surfaces

    Scenario: The inventory is enumerable and complete
      Given a deployed environment
      When its components are enumerated
      Then exactly the HTTP API service, the web application, the index database and the blob store SHALL be present

    Scenario: A component restarts without taking the others down
      Given all four components are running
      When any one of them is restarted
      Then the remaining three SHALL continue running
      And the restarted component SHALL return to serving without manual intervention

  Rule: The command line and the agent server are never hosted

    Scenario: No network listener for the agent server
      Given the agent server is running on a developer machine
      When its open network ports are inspected
      Then it SHALL be listening on none

    Scenario: Local tools work with the hosted environment unreachable
      Given every hosted component is unreachable
      When a developer validates an export and asks the agent server where an asset lives
      Then both SHALL complete normally

    Scenario: Hosting the agent surface is a specification change
      Given a request to expose the agent surface over the network
      When the deployed inventory is checked against this specification
      Then the deployment SHALL be rejected as non-conforming

  Rule: Configuration comes only from the environment

    Scenario: A configuration file is not consulted
      Given a required setting is absent from the environment
      And a file containing a value for that setting is present in the image and on a mounted volume
      When the service starts
      Then it SHALL treat the setting as absent

    Scenario: Changing a setting requires no new artifact
      Given a running deployment
      When an environment value is changed and the service is restarted
      Then the new value SHALL take effect
      And no new deployable artifact SHALL be produced

  Rule: No secret is carried in the repository or in a deployable artifact

    Scenario: Artifact inspection reveals no secret
      Given a deployable artifact for any hosted service
      When its contents are searched for the values of the declared secret settings
      Then none SHALL be found

    Scenario: Repository inspection reveals no secret
      When the repository is scanned for credentials at any revision reachable from the default branch
      Then none SHALL be found
      And the scan SHALL be part of the automated checks that gate a merge

  Rule: One artifact is built once and promoted unchanged

    Scenario: Promotion preserves the digest
      Given an artifact verified in a pre-production environment with a recorded digest
      When that revision is promoted to production
      Then the digest of the running artifact SHALL equal the recorded digest

    Scenario: Rollback selects a previously built artifact
      Given a deployment of a revision that must be withdrawn
      When the previous revision's recorded digest is deployed
      Then the previous version SHALL serve traffic
      And no rebuild SHALL be required

  Rule: A service with invalid configuration fails to start and says why

    Scenario: Missing setting names itself
      Given two required settings are absent from the environment
      When the service starts
      Then startup SHALL fail
      And the failure message SHALL name both absent settings

    Scenario: Malformed value is refused at boot, not at first request
      Given a required setting whose value cannot be interpreted as the type it declares
      When the service starts
      Then startup SHALL fail naming that setting and its expected shape
      And no request SHALL have been served

    Scenario: Optional configuration absent is not a startup failure
      Given the language model configuration is absent and the master switch is off
      When the service starts
      Then startup SHALL succeed
      And the model-dependent features SHALL report themselves unavailable

    Scenario: Secret values are not echoed
      Given a required secret setting is present but malformed
      When startup fails
      Then the message SHALL name the setting
      And SHALL NOT contain its value

  Rule: Liveness and readiness are distinct signals

    Scenario: Live but not ready during warm-up
      Given a service whose own datastore is not yet reachable
      When both signals are read
      Then liveness SHALL report responsive
      And readiness SHALL report not ready

    Scenario: Liveness performs no dependency access
      Given every dependency of a service is unreachable
      When the liveness signal is read
      Then it SHALL answer within its normal response time and report responsive

    Scenario: Not ready withholds traffic instead of restarting
      Given a running instance reporting not ready
      When the deployment platform evaluates it
      Then no request SHALL be routed to that instance
      And the instance SHALL NOT be terminated for reporting not ready

  Rule: Readiness never depends on an optional or sibling service

    Scenario: Model gateway outage does not block a deploy
      Given the configured language model endpoint is unreachable
      When a new version is deployed and its readiness is evaluated
      Then readiness SHALL report ready
      And the deploy SHALL complete
      And the status surface SHALL report the model-dependent features degraded

    Scenario: Identity provider outage does not block a deploy
      Given the identity provider is unreachable
      When readiness is evaluated
      Then readiness SHALL report ready
      And the status surface SHALL name the identity provider as unreachable

    Scenario: A lost working copy does withhold traffic
      Given the API service cannot reach a project's working copy volume
      When readiness is evaluated
      Then readiness SHALL report not ready, naming the working copy

    Scenario: A lost index does NOT withhold traffic
      Given the API service cannot reach the index database
      When readiness is evaluated
      Then readiness SHALL report ready
      And the status surface SHALL name the index as unavailable
      And answers derivable from the working copy alone SHALL continue to be served

    Scenario: The web application does not require the API to become ready
      Given the HTTP API service is unreachable
      When the web application is deployed and its readiness is evaluated
      Then readiness SHALL report ready
      And the application SHALL render a state describing the API as unavailable

  Rule: Index and working-copy freshness are observable without container access

    Scenario: Stale index is visible as stale
      Given the working copy has fetched a newer revision than the one the index was built from
      When the status surface is read
      Then it SHALL report the index as not matching the working copy
      And SHALL name both revisions

    Scenario: A silently failing fetch is detectable
      Given fetching has failed on every attempt for several scheduled intervals
      When the status surface is read
      Then the last successful fetch time SHALL be the time before the failures began
      And the most recent attempt SHALL be reported as failed with its time and reason

    Scenario: Freshness is answerable per project
      Given more than one project is configured
      When the status surface is read
      Then each project SHALL carry its own revision, fetch times and index-match state

  Rule: Migrations run as a release step with a defined failure state

    Scenario: Failed migration aborts the release
      Given a release whose migration fails
      When the release step completes
      Then it SHALL report failure
      And no instance of the new version SHALL have served a request
      And the previously deployed version SHALL still be serving

    Scenario: The schema version is reportable after a failure
      Given a migration failed partway through a release
      When the schema version is queried
      Then it SHALL report a recorded version
      And that version SHALL identify which migrations have been applied

    Scenario: Migrations do not run per instance
      Given a release that starts more than one instance
      When the instances start
      Then no instance SHALL attempt a migration

    Scenario: Recovery from a broken schema is a rebuild
      Given a schema left in a state no migration can advance
      When the documented recovery is performed
      Then the index SHALL be discarded, recreated at the target schema version and rebuilt from the working copies
      And the recovery SHALL NOT require a database backup

  Rule: Stateful components have persistent storage that survives redeploy

    Scenario: Redeploy preserves state
      Given an index built from a known revision and a working copy at that revision
      When a new artifact is deployed and the services restart
      Then the index SHALL still be built from that revision
      And the working copy SHALL still be at it
      And no rebuild SHALL have been triggered

    Scenario: Blobs outlive a restart
      Given a preview stored in the blob store
      When every service is restarted
      Then that preview SHALL still be retrievable by the same reference

  Rule: Losing any persistent volume is recoverable by rebuilding, and the procedure is tested

    Scenario: Index volume destroyed
      Given the index volume is deleted while the working copies are intact
      When the documented index recovery is performed
      Then lookups SHALL return the same results they returned before the loss
      And the elapsed time SHALL be recorded and compared against the stated expected duration

    Scenario: Blob volume destroyed
      Given the blob volume is deleted while the working copies are intact
      When the documented blob recovery is performed
      Then every blob derived from repository content SHALL be retrievable again by the same reference

    Scenario: Working copy destroyed
      Given a project's working copy volume is deleted
      When the documented working-copy recovery is performed
      Then the working copy SHALL be restored at the configured branch's current revision
      And the index and blob recoveries SHALL be able to run from it

    Scenario: Drills are executed, not assumed
      When the recovery documentation is inspected
      Then each of the three procedures SHALL carry the date and measured duration of its most recent execution

    Scenario: Degradation during recovery is bounded and visible
      Given an index rebuild is in progress
      When the status surface is read
      Then it SHALL report the rebuild as in progress
      And reads that cannot be served from the partial index SHALL report unavailability rather than an incomplete answer

  Rule: A deploy replaces instances without dropping requests

    Scenario: Continuous availability across a deploy
      Given a caller issuing read requests continuously
      When a new version is deployed and the previous version is retired
      Then every request SHALL receive a response
      And none SHALL fail because of the rollover

    Scenario: A retiring instance drains before terminating
      Given an instance with requests in flight is selected for retirement
      When retirement begins
      Then it SHALL stop accepting new requests
      And SHALL be allowed to complete in-flight requests until a bounded window expires

    Scenario: A never-ready new version does not replace the old one
      Given a new version whose readiness never reports ready
      When the deploy times out
      Then the previous version SHALL still be serving traffic

  Rule: An interrupted write-back leaves a commit or leaves nothing

    Scenario: Abandoned write-back leaves no partial edit
      Given a write-back that has modified a specification file but not yet committed
      When its instance is terminated before the drain window expires
      Then the working copy SHALL contain no uncommitted modification once the service is running again
      And the specification file SHALL match the configured branch

    Scenario: Success is reported only for a landed commit
      Given a write-back whose commit could not be pushed to the configured branch
      When the caller receives its response
      Then the response SHALL report failure
      And SHALL state that no change was recorded

    Scenario: Write-back completes within the drain window
      Given a write-back accepted just before retirement begins
      When it commits and pushes within the drain window
      Then the caller SHALL receive success
      And the commit SHALL exist on the configured branch attributed to the acting person

    Scenario: Only one write-back touches a project's working copy at a time
      Given two write-backs for the same project arrive while both an old and a new instance are running
      When they are processed
      Then they SHALL be applied one after the other
      And each SHALL produce its own commit, with neither overwriting the other's change
