# Spec Delta

## Purpose

Defines how CyberCanon runs as a hosted system: which surfaces are deployed and
which are deliberately never hosted, how a service is configured and how it
refuses to start when it is not, what "healthy" means without making another
team's outage into a failed deploy, and how persistent state is recovered by
rebuilding it rather than restoring it.

## ADDED Requirements

### Requirement: The hosted inventory is exactly the networked surfaces

The hosted deployment SHALL consist of exactly four components: the HTTP API
service, the web application, the index database, and the blob store. Each SHALL
be individually deployable, individually restartable, and reachable under the
studio's deployment host convention. No other component SHALL be added to the
hosted inventory without a specification change.

#### Scenario: The inventory is enumerable and complete
- **GIVEN** a deployed environment
- **WHEN** its components are enumerated
- **THEN** exactly the HTTP API service, the web application, the index database and the blob store SHALL be present

#### Scenario: A component restarts without taking the others down
- **GIVEN** all four components are running
- **WHEN** any one of them is restarted
- **THEN** the remaining three SHALL continue running
- **AND** the restarted component SHALL return to serving without manual intervention

### Requirement: The command line and the agent server are never hosted

The `canon` command line and the agent server SHALL NOT be deployed as
network-reachable services, in any environment, including behind authentication
or on a private network. The agent server SHALL communicate over a local
process-to-process channel only, and SHALL NOT listen on a network port. Both
SHALL remain fully usable against a developer's own working copy with no hosted
component reachable.

#### Scenario: No network listener for the agent server
- **GIVEN** the agent server is running on a developer machine
- **WHEN** its open network ports are inspected
- **THEN** it SHALL be listening on none

#### Scenario: Local tools work with the hosted environment unreachable
- **GIVEN** every hosted component is unreachable
- **WHEN** a developer validates an export and asks the agent server where an asset lives
- **THEN** both SHALL complete normally

#### Scenario: Hosting the agent surface is a specification change
- **GIVEN** a request to expose the agent surface over the network
- **WHEN** the deployed inventory is checked against this specification
- **THEN** the deployment SHALL be rejected as non-conforming

### Requirement: Configuration comes only from the environment

Every deployed service SHALL read its **service** configuration — endpoints,
credentials, connection strings, timeouts, feature switches — from environment
variables only. It SHALL NOT read service configuration from a file in the image,
from a file on a mounted volume, or from any other fallback source, and SHALL NOT
substitute a built-in default for a setting declared required.

Repository-authored, project-scoped configuration is **content, not service
configuration**: a project's own settings file inside its working copy is read as
repository content and is explicitly outside this requirement.

#### Scenario: A configuration file is not consulted
- **GIVEN** a required setting is absent from the environment
- **AND** a file containing a value for that setting is present in the image and on a mounted volume
- **WHEN** the service starts
- **THEN** it SHALL treat the setting as absent

#### Scenario: Changing a setting requires no new artifact
- **GIVEN** a running deployment
- **WHEN** an environment value is changed and the service is restarted
- **THEN** the new value SHALL take effect
- **AND** no new deployable artifact SHALL be produced

### Requirement: No secret is carried in the repository or in a deployable artifact

No credential, token, key or connection string SHALL be committed to the
repository or contained in a deployable artifact. Artifacts SHALL be free of
environment-specific values, so that inspecting an artifact reveals nothing about
where it is running.

#### Scenario: Artifact inspection reveals no secret
- **GIVEN** a deployable artifact for any hosted service
- **WHEN** its contents are searched for the values of the declared secret settings
- **THEN** none SHALL be found

#### Scenario: Repository inspection reveals no secret
- **WHEN** the repository is scanned for credentials at any revision reachable from the default branch
- **THEN** none SHALL be found
- **AND** the scan SHALL be part of the automated checks that gate a merge

### Requirement: One artifact is built once and promoted unchanged

A deployable artifact SHALL be built once per revision and promoted between
environments without rebuilding. The artifact running in a later environment
SHALL be identical to the one verified in an earlier environment, and identity
SHALL be verifiable by a content digest recorded at build time.

#### Scenario: Promotion preserves the digest
- **GIVEN** an artifact verified in a pre-production environment with a recorded digest
- **WHEN** that revision is promoted to production
- **THEN** the digest of the running artifact SHALL equal the recorded digest

#### Scenario: Rollback selects a previously built artifact
- **GIVEN** a deployment of a revision that must be withdrawn
- **WHEN** the previous revision's recorded digest is deployed
- **THEN** the previous version SHALL serve traffic
- **AND** no rebuild SHALL be required

### Requirement: A service with invalid configuration fails to start and says why

Every deployed service SHALL validate its required configuration before serving
any request. When a required setting is missing, or present but malformed, the
service SHALL fail to start, SHALL report a message naming every offending
setting and, for a malformed value, the expected shape, and SHALL NOT report
itself live or ready. A secret's value SHALL NOT appear in that message.

#### Scenario: Missing setting names itself
- **GIVEN** two required settings are absent from the environment
- **WHEN** the service starts
- **THEN** startup SHALL fail
- **AND** the failure message SHALL name both absent settings

#### Scenario: Malformed value is refused at boot, not at first request
- **GIVEN** a required setting whose value cannot be interpreted as the type it declares
- **WHEN** the service starts
- **THEN** startup SHALL fail naming that setting and its expected shape
- **AND** no request SHALL have been served

#### Scenario: Optional configuration absent is not a startup failure
- **GIVEN** the language model configuration is absent and the master switch is off
- **WHEN** the service starts
- **THEN** startup SHALL succeed
- **AND** the model-dependent features SHALL report themselves unavailable

#### Scenario: Secret values are not echoed
- **GIVEN** a required secret setting is present but malformed
- **WHEN** startup fails
- **THEN** the message SHALL name the setting
- **AND** SHALL NOT contain its value

### Requirement: Liveness and readiness are distinct signals

Every deployed service SHALL expose two separate signals. The liveness signal
SHALL report whether the process is running and responsive, and SHALL NOT perform
input or output against any dependency. The readiness signal SHALL report whether
the service can serve its own requests. A service that is live but not ready
SHALL NOT receive traffic and SHALL NOT be restarted for that reason alone.

#### Scenario: Live but not ready during warm-up
- **GIVEN** a service whose own datastore is not yet reachable
- **WHEN** both signals are read
- **THEN** liveness SHALL report responsive
- **AND** readiness SHALL report not ready

#### Scenario: Liveness performs no dependency access
- **GIVEN** every dependency of a service is unreachable
- **WHEN** the liveness signal is read
- **THEN** it SHALL answer within its normal response time and report responsive

#### Scenario: Not ready withholds traffic instead of restarting
- **GIVEN** a running instance reporting not ready
- **WHEN** the deployment platform evaluates it
- **THEN** no request SHALL be routed to that instance
- **AND** the instance SHALL NOT be terminated for reporting not ready

### Requirement: Readiness never depends on an optional or sibling service

A service's readiness SHALL depend only on the dependencies that service owns.
Readiness SHALL NOT depend on a language model endpoint, on the identity
provider, or on any sibling backend. When such a dependency is unreachable, the
service SHALL report ready and SHALL report the affected feature as degraded,
naming the dependency, so that another system's outage cannot cause a failed
deploy.

#### Scenario: Model gateway outage does not block a deploy
- **GIVEN** the configured language model endpoint is unreachable
- **WHEN** a new version is deployed and its readiness is evaluated
- **THEN** readiness SHALL report ready
- **AND** the deploy SHALL complete
- **AND** the status surface SHALL report the model-dependent features degraded

#### Scenario: Identity provider outage does not block a deploy
- **GIVEN** the identity provider is unreachable
- **WHEN** readiness is evaluated
- **THEN** readiness SHALL report ready
- **AND** the status surface SHALL name the identity provider as unreachable

#### Scenario: A lost working copy does withhold traffic
- **GIVEN** the API service cannot reach a project's working copy volume
- **WHEN** readiness is evaluated
- **THEN** readiness SHALL report not ready, naming the working copy

#### Scenario: A lost index does NOT withhold traffic
- **GIVEN** the API service cannot reach the index database
- **WHEN** readiness is evaluated
- **THEN** readiness SHALL report ready
- **AND** the status surface SHALL name the index as unavailable
- **AND** answers derivable from the working copy alone SHALL continue to be served

#### Scenario: The web application does not require the API to become ready
- **GIVEN** the HTTP API service is unreachable
- **WHEN** the web application is deployed and its readiness is evaluated
- **THEN** readiness SHALL report ready
- **AND** the application SHALL render a state describing the API as unavailable

### Requirement: Index and working-copy freshness are observable without container access

The deployment SHALL expose, per project, the revision the working copy is
currently at, the time of the last successful fetch, the outcome and time of the
most recent fetch attempt, the revision the index was last built from, and
whether the index matches the working copy's current revision. This information
SHALL be obtainable from the running system without a shell session inside a
container.

#### Scenario: Stale index is visible as stale
- **GIVEN** the working copy has fetched a newer revision than the one the index was built from
- **WHEN** the status surface is read
- **THEN** it SHALL report the index as not matching the working copy
- **AND** SHALL name both revisions

#### Scenario: A silently failing fetch is detectable
- **GIVEN** fetching has failed on every attempt for several scheduled intervals
- **WHEN** the status surface is read
- **THEN** the last successful fetch time SHALL be the time before the failures began
- **AND** the most recent attempt SHALL be reported as failed with its time and reason

#### Scenario: Freshness is answerable per project
- **GIVEN** more than one project is configured
- **WHEN** the status surface is read
- **THEN** each project SHALL carry its own revision, fetch times and index-match state

### Requirement: Migrations run as a release step with a defined failure state

Index schema migrations SHALL run as a release step that completes before any
instance of the new version serves traffic, and SHALL NOT run on service start.
When a migration fails, the release SHALL abort, no instance of the new version
SHALL serve traffic, the previously deployed version SHALL continue serving, and
the schema SHALL be left at a recorded version that the runner can report.

#### Scenario: Failed migration aborts the release
- **GIVEN** a release whose migration fails
- **WHEN** the release step completes
- **THEN** it SHALL report failure
- **AND** no instance of the new version SHALL have served a request
- **AND** the previously deployed version SHALL still be serving

#### Scenario: The schema version is reportable after a failure
- **GIVEN** a migration failed partway through a release
- **WHEN** the schema version is queried
- **THEN** it SHALL report a recorded version
- **AND** that version SHALL identify which migrations have been applied

#### Scenario: Migrations do not run per instance
- **GIVEN** a release that starts more than one instance
- **WHEN** the instances start
- **THEN** no instance SHALL attempt a migration

#### Scenario: Recovery from a broken schema is a rebuild
- **GIVEN** a schema left in a state no migration can advance
- **WHEN** the documented recovery is performed
- **THEN** the index SHALL be discarded, recreated at the target schema version and rebuilt from the working copies
- **AND** the recovery SHALL NOT require a database backup

### Requirement: Stateful components have persistent storage that survives redeploy

The index database, the blob store and each project's working copy SHALL be
backed by storage that survives a service restart, a redeploy and an artifact
promotion. After any of those events the system SHALL continue from its previous
state without re-running a recovery procedure.

#### Scenario: Redeploy preserves state
- **GIVEN** an index built from a known revision and a working copy at that revision
- **WHEN** a new artifact is deployed and the services restart
- **THEN** the index SHALL still be built from that revision
- **AND** the working copy SHALL still be at it
- **AND** no rebuild SHALL have been triggered

#### Scenario: Blobs outlive a restart
- **GIVEN** a preview stored in the blob store
- **WHEN** every service is restarted
- **THEN** that preview SHALL still be retrievable by the same reference

### Requirement: Losing any persistent volume is recoverable by rebuilding, and the procedure is tested

For each of the three persistent volumes there SHALL be a documented recovery
procedure with a stated expected duration: the index rebuilds from the working
copies, the blob store re-mirrors from them, and a working copy re-clones from
the git host. No recovery procedure SHALL depend on a backup of the index or of
the blob store. Each procedure SHALL be executed against a non-production
environment on a recurring basis, and its measured duration SHALL be recorded
alongside the procedure.

#### Scenario: Index volume destroyed
- **GIVEN** the index volume is deleted while the working copies are intact
- **WHEN** the documented index recovery is performed
- **THEN** lookups SHALL return the same results they returned before the loss
- **AND** the elapsed time SHALL be recorded and compared against the stated expected duration

#### Scenario: Blob volume destroyed
- **GIVEN** the blob volume is deleted while the working copies are intact
- **WHEN** the documented blob recovery is performed
- **THEN** every blob derived from repository content SHALL be retrievable again by the same reference

#### Scenario: Working copy destroyed
- **GIVEN** a project's working copy volume is deleted
- **WHEN** the documented working-copy recovery is performed
- **THEN** the working copy SHALL be restored at the configured branch's current revision
- **AND** the index and blob recoveries SHALL be able to run from it

#### Scenario: Drills are executed, not assumed
- **WHEN** the recovery documentation is inspected
- **THEN** each of the three procedures SHALL carry the date and measured duration of its most recent execution

#### Scenario: Degradation during recovery is bounded and visible
- **GIVEN** an index rebuild is in progress
- **WHEN** the status surface is read
- **THEN** it SHALL report the rebuild as in progress
- **AND** reads that cannot be served from the partial index SHALL report unavailability rather than an incomplete answer

### Requirement: A deploy replaces instances without dropping requests

Deploying a new version SHALL NOT produce a failed request for a caller of an
already-supported operation. A new instance SHALL receive traffic only after it
reports ready, and an instance being retired SHALL stop receiving new requests
before it terminates and SHALL be given a bounded window to finish the requests
it already accepted.

#### Scenario: Continuous availability across a deploy
- **GIVEN** a caller issuing read requests continuously
- **WHEN** a new version is deployed and the previous version is retired
- **THEN** every request SHALL receive a response
- **AND** none SHALL fail because of the rollover

#### Scenario: A retiring instance drains before terminating
- **GIVEN** an instance with requests in flight is selected for retirement
- **WHEN** retirement begins
- **THEN** it SHALL stop accepting new requests
- **AND** SHALL be allowed to complete in-flight requests until a bounded window expires

#### Scenario: A never-ready new version does not replace the old one
- **GIVEN** a new version whose readiness never reports ready
- **WHEN** the deploy times out
- **THEN** the previous version SHALL still be serving traffic

### Requirement: An interrupted write-back leaves a commit or leaves nothing

A write-back that is in flight when its instance is retired SHALL either complete
as a commit on the configured branch or leave no trace at all. A partially
written file SHALL NOT remain in the working copy, and a caller SHALL NOT be told
a write-back succeeded unless its commit exists on the configured branch. On
startup, and after any failed write-back, the working copy SHALL be returned to
the state of the configured branch, discarding any uncommitted change.

#### Scenario: Abandoned write-back leaves no partial edit
- **GIVEN** a write-back that has modified a specification file but not yet committed
- **WHEN** its instance is terminated before the drain window expires
- **THEN** the working copy SHALL contain no uncommitted modification once the service is running again
- **AND** the specification file SHALL match the configured branch

#### Scenario: Success is reported only for a landed commit
- **GIVEN** a write-back whose commit could not be pushed to the configured branch
- **WHEN** the caller receives its response
- **THEN** the response SHALL report failure
- **AND** SHALL state that no change was recorded

#### Scenario: Write-back completes within the drain window
- **GIVEN** a write-back accepted just before retirement begins
- **WHEN** it commits and pushes within the drain window
- **THEN** the caller SHALL receive success
- **AND** the commit SHALL exist on the configured branch attributed to the acting person

#### Scenario: Only one write-back touches a project's working copy at a time
- **GIVEN** two write-backs for the same project arrive while both an old and a new instance are running
- **WHEN** they are processed
- **THEN** they SHALL be applied one after the other
- **AND** each SHALL produce its own commit, with neither overwriting the other's change
