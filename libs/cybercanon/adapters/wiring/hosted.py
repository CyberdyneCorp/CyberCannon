"""The hosted composition root: the configuration, as an application that serves.

:mod:`cybercanon.adapters.wiring.build` builds the container a person's laptop
runs against. This builds the one a deployment runs against, and the difference
between the two is the whole of the hosted story: a persistent working copy on a
volume instead of the directory somebody is standing in, PostgreSQL instead of
SQLite, an S3 API instead of a folder under `.canon`, and an address the project
is served at instead of whatever the working copy calls itself.

**Nothing here reaches anything.** A process that connected to PostgreSQL in
order to start would turn one dependency's outage into a crash loop, and
`deployment-operations` requires the opposite in so many words: `/readyz` has to
be able to answer *not ready, the index is unreachable*, which a process that
never started cannot say. So every stateful adapter is wrapped in
:class:`Deferred`, which builds it the first time somebody calls it and drops it
again when a call fails — and :func:`observations` is what turns *did that work*
into the readiness signal, at the moment readiness is asked rather than at boot.

**One project, named by configuration.** `CANON_REPOSITORY_URL` is one remote,
so a deployment serves one project, and `CANON_PROJECT` is the identifier it
serves it as. That identifier is the address `http-api` makes permanent, and it
is therefore also what the entitlement decision, the index rows and the
working-copy directory are keyed by — see
:attr:`~cybercanon.adapters.wiring.container.Container.project_id`. Deriving it
from the repository URL, or from the working copy's `.canon/project.yaml`, was
the alternative, and it is the one that produces the bug: a repository called
`ronin` whose project declares itself `Ronin`, and half the endpoints refusing
an actor the other half accepted.

**What is deliberately not wired.** There is no `Notifier`: `asset-requests`'
D9 makes an unread item a *derived query* — the requests where a person is the
author or the assignee, minus that person's dismissals — so the durable half is
repository content and the forgettable half is the `Dismissals` store, which is
wired. A notifier here would be a second place notification state lived, and
there is no destination configured for one to send to.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import boto3
from botocore.config import Config

from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.inbound.http.webhooks import RepositoryNotifications
from cybercanon.adapters.outbound.auth.flows import ServiceCredentials
from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.adapters.outbound.postgres.dismissals import PostgresDismissals
from cybercanon.adapters.outbound.postgres.idempotency import PostgresIdempotencyStore
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring.background import BackgroundWork, Ticker, validation_job
from cybercanon.adapters.wiring.build import (
    arche_settings,
    document_platform,
    file_fingerprints,
    language_model,
    preview_settings,
    vision_model,
)
from cybercanon.adapters.wiring.configuration import ServiceConfiguration
from cybercanon.adapters.wiring.container import Container
from cybercanon.adapters.wiring.identity import WiredIdentity, background_identity
from cybercanon.application.ports.clock import system_clock
from cybercanon.application.use_cases.deployment_status import (
    DeploymentJournal,
    refresh_and_record,
)
from cybercanon.application.use_cases.service_health import (
    OBJECT_STORE,
    SEARCH_INDEX,
    WORKING_COPY,
    ComponentStatus,
    available,
    unavailable,
)

DEFAULT_BUCKET = "cybercanon"
"""What the blob mirror is called when the object store URL names no bucket."""

INDEX_REACHABLE = "the index answered"
BLOBS_REACHABLE = "the blob mirror answered"

ALIVE_QUERY = "SELECT 1"
"""The cheapest question a readiness probe can ask a database."""

MAX_ATTEMPTS = 3
"""How hard boto3 retries one call before the probe calls the store unreachable."""


# --------------------------------------------------------------------------
# Deferred construction — build on first use, drop on failure
# --------------------------------------------------------------------------


class Deferred:
    """An adapter built the first time it is called, and rebuilt after a failure.

    It exists for one sentence of `deployment-operations`: *"`/readyz` ... not
    ready — naming the component — with the index unreachable"*. A process that
    opened its database connection at import time cannot say that, because it is
    not running; one that opens it on first use says it every time it is asked.

    Dropping the delegate when a call raises is the other half: a connection
    that died with the database it pointed at is not a connection, and a process
    that kept it would stay broken until somebody restarted it — which is
    exactly the restart a rebuildable index is supposed to make unnecessary.
    """

    def __init__(self, build: Callable[[], Any], name: str = "") -> None:
        self._build = build
        self._name = name
        self._made: Any = None

    @property
    def name(self) -> str:
        return self._name

    def delegate(self) -> Any:
        """The adapter, building it if this is the first call."""
        if self._made is None:
            self._made = self._build()
        return self._made

    def forget(self) -> None:
        """Drop the delegate so the next call builds a new one."""
        self._made = None

    def __getattr__(self, attribute: str) -> Any:
        if attribute.startswith("_"):
            raise AttributeError(attribute)
        value = getattr(self.delegate(), attribute)
        return _guarded(self, value) if callable(value) else value


def _guarded(deferred: Deferred, call: Callable[..., Any]) -> Callable[..., Any]:
    """One call on a deferred adapter, dropping the delegate when it fails."""

    def guarded(*arguments: Any, **keywords: Any) -> Any:
        try:
            return call(*arguments, **keywords)
        except Exception:
            deferred.forget()
            raise

    return guarded


def probe(deferred: Deferred, check: Callable[[Any], None], detail: str) -> ComponentStatus:
    """Ask one deferred adapter whether it is there, and never raise doing it.

    The probe is what `/readyz` reports, so its failure is an *answer* rather
    than an error: a readiness endpoint that raised because a dependency was
    down would report nothing at the moment it is most needed.
    """
    try:
        check(deferred.delegate())
    except Exception as failure:
        deferred.forget()
        return unavailable(deferred.name, f"{type(failure).__name__}: {failure}")
    return available(deferred.name, detail)


# --------------------------------------------------------------------------
# The object store's connection settings, out of one URL
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ObjectStore:
    """Where the blob mirror is, read out of `CANON_OBJECT_STORE_URL`.

    The URL carries everything, because Coolify supplies one variable per
    setting and a blob store needs four: the scheme and host are the endpoint,
    the user-info half is the access key and its secret, and the first path
    segment is the bucket. That is the shape `deploy/e2e/compose.yaml` already
    uses, so the deployment and the end-to-end stack are configured identically.
    """

    endpoint: str
    bucket: str = DEFAULT_BUCKET
    access_key: str = ""
    secret_key: str = ""

    @property
    def base_url(self) -> str:
        return f"{self.endpoint}/{self.bucket}"


def object_store(url: str) -> ObjectStore:
    """The endpoint, the credential and the bucket, from one configured URL."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    bucket = parsed.path.strip("/").split("/")[0]
    return ObjectStore(
        endpoint=f"{parsed.scheme}://{host}{port}",
        bucket=bucket or DEFAULT_BUCKET,
        access_key=unquote(parsed.username or ""),
        secret_key=unquote(parsed.password or ""),
    )


@dataclass(frozen=True)
class WiredBlobs:
    """The mirror and the client it speaks through, so a probe has something to ask.

    Two references rather than reaching into the store, because the store's
    client is its own business: the readiness probe asks the *client* whether
    the bucket is there, and the use cases ask the *store* for previews.
    """

    store: S3BlobStore
    client: Any
    settings: ObjectStore

    def reachable(self) -> None:
        """Raise unless the configured bucket is there right now."""
        self.client.head_bucket(Bucket=self.settings.bucket)


def blob_store(settings: ObjectStore, secret: bytes = b"") -> WiredBlobs:
    """The mirror, over a boto3 client this function is the only builder of.

    Constructing a client opens no connection, so the cost of building one is a
    few objects; what has to stay deferred is everything that would talk to it.
    """
    client = boto3.client(
        "s3",
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key or None,
        aws_secret_access_key=settings.secret_key or None,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
        ),
    )
    store = S3BlobStore(client, settings.bucket, base_url=settings.base_url, secret=secret)
    return WiredBlobs(store=store, client=client, settings=settings)


# --------------------------------------------------------------------------
# The deployment
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HostedDeployment:
    """Everything the process holds: what serves, what refreshes, what validates.

    One object so a test can build the whole deployment from a configuration and
    then assert over its parts, and so the process entry point has one thing to
    start and one thing to stop.
    """

    configuration: ServiceConfiguration
    surface: Surface
    notifications: RepositoryNotifications
    work: BackgroundWork
    schedule: Ticker
    journal: DeploymentJournal
    repository_host: GitRepositoryHost
    sync: Callable[[str], object]

    @property
    def project(self) -> str:
        return self.configuration.repository.project

    def start(self) -> HostedDeployment:
        """Begin the background runner and the fetch schedule. Idempotent."""
        self.work.start()
        self.schedule.start()
        return self

    def stop(self) -> None:
        self.schedule.stop()
        self.work.stop()


def repository_host(
    configuration: ServiceConfiguration, environment: Mapping[str, str] | None = None
) -> GitRepositoryHost:
    """The working-copy volume, with this deployment's one project declared on it.

    Declaring a project is not cloning it: it is `provisioning` until something
    asks, which is what lets the process start on a volume that has just been
    created — or on one whose contents a recovery is about to replace.
    """
    repository = configuration.repository
    return GitRepositoryHost(
        Path(repository.working_copies),
        remotes=(
            ProjectRemote(
                project=repository.project,
                url=repository.url,
                branch=repository.branch,
                credential=repository.credential.value,
            ),
        ),
        environment=dict(environment or {}),
    )


def build_deployment(
    configuration: ServiceConfiguration,
    *,
    identity: WiredIdentity | None = None,
    worker: ServiceCredentials | None = None,
    environment: Mapping[str, str] | None = None,
    observed: Callable[[], Sequence[ComponentStatus]] = tuple,
) -> HostedDeployment:
    """The whole hosted application, from the configuration and nothing else.

    `observed` reports the components this module did not wire — the language
    model, the identity service — and what it returns is prepended to what the
    probes find, so `/readyz` and `/status` read one list rather than two that
    have to be reconciled.

    `worker` is how background work obtains a credential of its own
    (`CANON_WORKER_CLIENT_ID` and its secret). ``None`` — the deployment that
    configured neither — is the behaviour this had before: the pass runs and is
    recorded as automation. Nothing is obtained here, at build time; the
    exchange happens at the first pass, because a boot that needed the identity
    service to be up is the cascade D8 exists to prevent.
    """
    repository = configuration.repository
    project = repository.project
    host = repository_host(configuration, environment)
    root = host.path(project)
    dsn = configuration.storage.database_url.value

    index = Deferred(lambda: PostgresSearchIndex(dsn), SEARCH_INDEX)
    blobs = Deferred(
        lambda: blob_store(object_store(configuration.storage.object_store_url)), OBJECT_STORE
    )
    container = _container(root, index=index, blobs=blobs, project=project, environment=environment)
    journal = DeploymentJournal()
    work = BackgroundWork(
        validation_job(
            container,
            host,
            background_identity(worker, provider=identity.provider if identity else None),
        )
    )
    sync = _sync(host, journal, work)
    surface = Surface(
        projects={
            project: HostedProject(
                name=project,
                container=container,
                repository_host=host,
                interval=repository.fetch_interval,
            )
        },
        identity_provider=identity.provider if identity else None,
        idempotency=Deferred(lambda: PostgresIdempotencyStore(dsn)),
        dismissals=Deferred(lambda: PostgresDismissals(dsn)),
        journal=journal,
        web_origins=configuration.browser.origins,
        observe=lambda: (*observed(), *observations(index, blobs)),
    )
    return HostedDeployment(
        configuration=configuration,
        surface=surface,
        notifications=RepositoryNotifications(
            secret=repository.webhook_secret.value,
            branches={project: repository.branch},
            refresh=sync,
        ),
        work=work,
        schedule=Ticker(lambda: sync(project), repository.fetch_interval),
        journal=journal,
        repository_host=host,
        sync=sync,
    )


def _container(
    root: Path,
    *,
    index: Deferred,
    blobs: Deferred,
    project: str,
    environment: Mapping[str, str] | None = None,
) -> Container:
    """The container every surface of this deployment runs against.

    The mesh inspector is deferred with the rest: its decimation settings come
    from the project's own `.canon/project.yaml` (D7), which is repository
    content on a volume that may not have been cloned yet. Reading it at boot
    would make the process depend on the clone having finished.

    The document platform is chosen here exactly as it is for `canon` — one
    call, and the null adapter whenever configuration is absent or incomplete
    (add-cyberarche-integration D4). It is *not* deferred: choosing it opens
    nothing, and a deployment that never configured it must behave as though
    this change had never been made.

    The two model ports are chosen the same way and for the same reason
    (`add-derived-metadata`). `CANON_LLM_ENABLED` defaults to off, and a
    deployment that leaves it off gets the disabled ports — which answer every
    call with *disabled* rather than failing, so readiness, validation,
    compilation and lookup are untouched by whether a gateway is reachable.
    """
    spec_store = GitSpecStore(root)
    return Container(
        spec_store=spec_store,
        mesh_inspector=Deferred(lambda: _inspector(spec_store, root)),
        blob_store=Deferred(lambda: blobs.delegate().store),
        search_index=index,
        fingerprints=file_fingerprints(root),
        project_id=project,
        document_platform=document_platform(environment),
        document_workspace=arche_settings(environment).default_workspace,
        document_budget=arche_settings(environment).timeout,
        llm=language_model(environment),
        vision=vision_model(environment),
    )


def _inspector(spec_store: GitSpecStore, root: Path) -> TrimeshInspector:
    return TrimeshInspector(
        root=root, settings=preview_settings(spec_store.load_project("").preview)
    )


def _sync(
    host: GitRepositoryHost, journal: DeploymentJournal, work: BackgroundWork
) -> Callable[[str], object]:
    """Obtain the working copy, refresh it, and queue the validation pass (G1).

    One function for both drivers, because D4 makes the schedule the guarantee
    and the webhook only the thing that shortens the wait — two implementations
    would be two definitions of *up to date*. The clone comes first and is
    re-entrant: a volume that already holds the copy is adopted rather than
    re-obtained, and a volume that has just been created is filled here rather
    than by the first request that needed it.

    Nothing raises out of this. A remote that cannot be reached is an attempt
    the journal records as failed, with the reason `/status` reports, and the
    project keeps answering from whatever revision it already had.
    """

    def sync(project: str) -> object:
        obtained = _obtain(project, host, journal)
        if obtained is not None:
            return obtained
        outcome = refresh_and_record(project, repository_host=host, journal=journal)
        work.submit(project)
        return outcome

    return sync


def _obtain(
    project: str, host: GitRepositoryHost, journal: DeploymentJournal
) -> ComponentStatus | None:
    """Clone the working copy when it is not there, journalling a failure to."""
    try:
        host.clone(project)
    except Exception as failure:
        reason = getattr(failure, "reason", "") or f"{type(failure).__name__}"
        journal.attempted(project, at=system_clock(), succeeded=False, reason=reason)
        return unavailable(WORKING_COPY, reason)
    return None


def observations(index: Deferred, blobs: Deferred) -> tuple[ComponentStatus, ...]:
    """The two dependencies readiness is allowed to consult, asked right now.

    Task 2.3 names them: *"`/readyz` for the API checking only the index
    database and the blob store"*. The working copy is deliberately **not**
    here. It is reported per project on `/status`, where an operator reads it;
    consulting it for readiness would mean a freshly provisioned volume never
    becomes ready, the platform never routes to the instance, and the schedule
    that would have cloned it never gets to run — a deploy that cannot complete
    because it has not completed.

    Neither of these gates either
    (:data:`~cybercanon.application.use_cases.service_health.RELIANCE` calls
    both rebuildable), so what they produce is a *degraded* list. That
    classification is the application layer's and is not re-decided here; this
    function only reports what it found.
    """
    return (
        probe(index, _index_answers, INDEX_REACHABLE),
        probe(blobs, lambda wired: wired.reachable(), BLOBS_REACHABLE),
    )


def _index_answers(store: PostgresSearchIndex) -> None:
    store.connection.execute(ALIVE_QUERY)


__all__ = [
    "ALIVE_QUERY",
    "BLOBS_REACHABLE",
    "DEFAULT_BUCKET",
    "INDEX_REACHABLE",
    "Deferred",
    "HostedDeployment",
    "ObjectStore",
    "WiredBlobs",
    "blob_store",
    "build_deployment",
    "object_store",
    "observations",
    "probe",
    "repository_host",
]
