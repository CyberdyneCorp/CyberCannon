"""The hosted API serves a project, and it reaches nothing to be able to say so.

Before this suite the deployable built `build_app(container=None, surface=...)`
with no projects, no idempotency store and no dismissals: it answered `/healthz`
and `/readyz` and served nothing at all. Every address under
`/v1/projects/{project}` was a not-found, on a process that reported itself
ready — which is the failure mode a health endpoint is supposed to prevent and
was instead concealing.

Two properties, and they pull in opposite directions, which is why both are
here:

* **it is wired** — one project, at the address `CANON_PROJECT` names, with the
  index, the blob mirror, the idempotency store, the dismissal store, the
  webhook secret and the browser origins the configuration carries;
* **it reaches nothing** — no database connection, no S3 call, no clone, no
  network of any kind happens while the application is being built. The suite
  runs with every one of those pointed at an address that does not resolve, and
  a process that tried to reach one would fail here rather than in a deploy.

The two together are the whole requirement: *"readiness must still be answerable
by a process given nothing"*, without that being achieved by giving it nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cybercanon.adapters.inbound.http.health import ALIVE, LIVE_PATH, READY, READY_PATH
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.inbound.http.webhooks import WEBHOOK_PATH
from cybercanon.adapters.wiring.configuration import ServiceConfiguration, load
from cybercanon.adapters.wiring.hosted import (
    Deferred,
    HostedDeployment,
    build_deployment,
    object_store,
)
from cybercanon.api.main import build_for

pytestmark = pytest.mark.unit

PROJECT = "ronin"
BRANCH = "canon"
SECRET = "a-shared-secret"  # not-a-credential: a literal in a test
ORIGIN = "https://canon.backend.coolify.cyberdynecorp.ai"

UNRESOLVABLE = "unresolvable.invalid"
"""Every dependency points here. Reaching one is a failure the suite can see."""

BLOBS = f"http://canon:blobs@{UNRESOLVABLE}:9000/canon"  # not-a-credential
"""The mirror's four settings in one URL, at a host that does not resolve."""


def an_environment(**overrides: str) -> dict[str, str]:
    """A complete configuration whose every dependency is unreachable on purpose."""
    return {
        "CANON_PROJECT": PROJECT,
        "CANON_REPOSITORY_URL": f"https://{UNRESOLVABLE}/cyberdynecorp/ronin.git",
        "CANON_REPOSITORY_BRANCH": BRANCH,
        "CANON_REPOSITORY_CREDENTIAL": "a-deploy-key",  # not-a-credential
        "CANON_FETCH_INTERVAL_S": "300",
        "CANON_WEBHOOK_SECRET": SECRET,
        "CANON_AUTH_ISSUER": f"https://{UNRESOLVABLE}",
        "CANON_AUTH_AUDIENCE": "cybercanon",
        "CANON_AUTH_KEY_SET_URL": f"https://{UNRESOLVABLE}/.well-known/jwks.json",
        "CANON_AUTH_GROUP_ROLES": "canon-art=ART_DIRECTOR",
        "CANON_DATABASE_URL": f"postgresql://canon@{UNRESOLVABLE}:5432/canon",
        "CANON_OBJECT_STORE_URL": BLOBS,
        "CANON_LINK_EXPIRY_S": "300",
        "CANON_WRITE_BACK_TIMEOUT_S": "30",
        "CANON_DRAIN_WINDOW_S": "60",
        "CANON_WEB_ORIGINS": ORIGIN,
    } | overrides


@pytest.fixture
def configuration(tmp_path: Path) -> ServiceConfiguration:
    return load(an_environment(CANON_WORKING_COPIES=str(tmp_path / "worktrees")))


@pytest.fixture
def deployment(configuration: ServiceConfiguration) -> HostedDeployment:
    """The wiring, built and never started: no thread, no clone, no schedule."""
    return build_deployment(configuration)


# --------------------------------------------------------------------------
# It is wired
# --------------------------------------------------------------------------


def test_the_deployment_serves_the_project_its_configuration_names(
    deployment: HostedDeployment,
) -> None:
    assert deployment.surface.project_names() == (PROJECT,)
    assert deployment.project == PROJECT


def test_the_project_is_identified_by_the_address_everywhere_underneath(
    deployment: HostedDeployment,
) -> None:
    """`CANON_PROJECT` is the address, and therefore the entitlement subject and
    the key the index rows are written under — one string, not three."""
    hosted = deployment.surface.projects[PROJECT]

    assert hosted.name == PROJECT
    assert hosted.container.project_id == PROJECT
    assert hosted.container.project_name == PROJECT


def test_the_working_copy_lives_under_the_configured_volume(
    deployment: HostedDeployment, configuration: ServiceConfiguration
) -> None:
    volume = Path(configuration.repository.working_copies)

    assert deployment.repository_host.path(PROJECT) == volume / PROJECT
    assert deployment.repository_host.remote_of(PROJECT).branch == BRANCH


def test_every_stateful_port_the_surface_needs_is_wired(
    deployment: HostedDeployment,
) -> None:
    """The three the deployable used to pass as ``None``, and the fourth it never had."""
    surface = deployment.surface
    container = surface.projects[PROJECT].container

    assert surface.idempotency is not None
    assert surface.dismissals is not None
    assert container.search_index is not None
    assert container.blob_store is not None


def test_the_notification_endpoint_is_configured_with_the_secret_and_the_branch(
    deployment: HostedDeployment,
) -> None:
    assert deployment.notifications.secret == SECRET
    assert deployment.notifications.branches == {PROJECT: BRANCH}


def test_the_browser_origins_reach_the_surface(deployment: HostedDeployment) -> None:
    assert deployment.surface.web_origins == (ORIGIN,)


def test_the_object_store_url_carries_endpoint_credential_and_bucket() -> None:
    """One variable, four settings — the shape `deploy/e2e/compose.yaml` already uses."""
    settings = object_store("http://canon:blobs@minio:9000/canon-blobs")  # not-a-credential

    assert settings.endpoint == "http://minio:9000"
    assert settings.bucket == "canon-blobs"
    assert settings.access_key == "canon"
    assert settings.secret_key == "blobs"  # not-a-credential


# --------------------------------------------------------------------------
# It reaches nothing
# --------------------------------------------------------------------------


def test_building_the_application_opens_no_connection_to_anything(
    configuration: ServiceConfiguration,
) -> None:
    """Every dependency is at an address that does not resolve, and it still builds.

    If any of them were contacted here, this test would not be slow — it would
    fail, which is the point: a boot that needed PostgreSQL to be up turns one
    dependency's outage into a crash loop nobody can read a health endpoint
    through.
    """
    client = _client(build_for(configuration))

    assert client.get(LIVE_PATH).json()["status"] == ALIVE


def test_readiness_answers_with_the_index_and_the_mirror_unreachable(
    configuration: ServiceConfiguration,
) -> None:
    """`deployment-operations`: both are rebuildable, so neither withholds traffic —
    and both are *named* as degraded, so an operator is not left guessing."""
    answered = _client(build_for(configuration)).get(READY_PATH)

    body = answered.json()
    assert body["status"] == READY, body
    assert {"search_index", "object_store"} <= set(body["degraded"]), body


def test_an_unconfigured_working_copy_is_a_not_found_and_not_a_crash(
    configuration: ServiceConfiguration,
) -> None:
    """A project the deployment does not serve is still a not-found, as before."""
    answered = _client(build_for(configuration)).get(f"/{VERSION}/projects/someone-else/assets")

    assert answered.status_code == 404, answered.text


def test_the_notification_endpoint_exists_once_a_secret_is_configured(
    configuration: ServiceConfiguration,
) -> None:
    """Unsigned, so it is refused — but it is *there*, which it was not before."""
    answered = _client(build_for(configuration)).post(WEBHOOK_PATH, content=b"{}")

    assert answered.status_code != 404, answered.text


def _client(application: Any) -> Any:
    """A client that does **not** enter the lifespan.

    Deliberate: the lifespan is where the fetch schedule starts, and these tests
    are about what building the application does and does not do. Entering it
    would have the process try to clone from an address that does not resolve,
    which is the schedule working correctly and has nothing to say here.
    """
    from fastapi.testclient import TestClient

    return TestClient(application)


# --------------------------------------------------------------------------
# Deferred construction, on its own
# --------------------------------------------------------------------------


def test_a_deferred_adapter_is_not_built_until_it_is_used() -> None:
    built: list[int] = []
    deferred = Deferred(lambda: built.append(1) or "made", "thing")

    assert built == []
    assert deferred.delegate() == "made"
    assert built == [1]


def test_a_deferred_adapter_is_rebuilt_after_a_call_fails() -> None:
    """A connection that died with the database it pointed at is not a connection."""
    made: list[object] = []

    class Flaky:
        def __init__(self) -> None:
            made.append(self)

        def ask(self) -> None:
            raise RuntimeError("the database went away")

    deferred = Deferred(Flaky, "index")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            deferred.ask()

    assert len(made) == 2, "the failed delegate was kept and reused"
