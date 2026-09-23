"""Step definitions for `deployment-operations` — every group of the change.

It starts with the two requirements the change exists for: **configuration
comes only from the environment and a bad one stops the boot**, and **liveness,
readiness and the status surface are three different things**. The release
step, the volumes, the rollover, the drills and the hosted inventory follow, in
the order of the change's own task groups.

What is driven here is the real thing in every case that has one: the real
loader over a mapping that is not the process environment, the real FastAPI
application over in-memory fakes, the real readiness classification, the real
status surface with a real credential. Nothing is asserted against a mock of
CyberCanon.

One scenario is not a Python call and is asserted the way a deployment is read
rather than pretended: *"Not ready withholds traffic instead of restarting"* is
a property of two signals and of which probe the platform is pointed at, so it
is asserted as both — readiness answers a status class a routing gate withholds
traffic on, liveness keeps answering responsive, and `deploy/README.md` points
the restart probe at liveness and the routing gate at readiness.

One scenario of these two requirements stays **deliberately pending**: *"The web
application does not require the API to become ready"*, and what is still
missing is now only half of it. Its readiness *is* executed against the running
artifact — `tests/integration/test_web_readiness_process.py` starts the built
application with nothing answering at the address of the API, reads `/readyz`,
and asserts the process never opened a connection to that address. What no
Python step can execute is the scenario's second half, *"the application SHALL
render a state describing the API as unavailable"*: the frame renders in the
browser (`ssr = false`, a session decision), so the render is executed by
`apps/cybercanon/web/tests/availability.test.ts` under `web-check` and, in a
real browser, by the end-to-end layer. A step that asserted the first half and
read the source for the second would be claiming to have seen something this
process did not render, so the line stays on the pending list until an
end-to-end run can ask a browser.

Groups 3 to 8 are here too, below, and what is left on `tests/bdd/pending.txt`
for this capability is three lines: the two artifact scenarios, whose
confirmations are a container engine's rather than this process's, and the web
application's readiness, for the reason above.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, scenario, then, when

from canon_deploy import inventory as deployed
from canon_deploy.__main__ import web_variables
from canon_drill.records import PROCEDURES, drills, expectations, latest
from canon_lint import secrets
from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.health import (
    ALIVE,
    DEGRADED_FIELD,
    DEPENDENCIES_FIELD,
    LIVE_PATH,
    NOT_READY,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.inbound.http.status import PROJECTS_FIELD, STATUS_PATH
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.git import commands
from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.postgres import migrations
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring import configuration
from cybercanon.adapters.wiring.configuration import (
    ConfigurationIncomplete,
    ConfigurationInvalid,
    ConfigurationRejected,
)
from cybercanon.adapters.wiring.container import Container
from cybercanon.api import main, migrate, recover
from cybercanon.api.main import application
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.results import succeeded
from cybercanon.application.testing import build_fakes
from cybercanon.application.use_cases.blob_mirror import mirror_project
from cybercanon.application.use_cases.deployment_status import (
    INDEX_REBUILDING,
    DeploymentJournal,
    refresh_and_record,
)
from cybercanon.application.use_cases.hosted_repository import (
    NOTHING_RECORDED,
    Edit,
    resume_project,
    write_back,
)
from cybercanon.application.use_cases.service_health import (
    IDENTITY_SERVICE,
    LANGUAGE_MODEL,
    OBJECT_STORE,
    SEARCH_INDEX,
    WORKING_COPY,
    available,
    unavailable,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.revisions import ContentHash

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "ironwood"

SCOUT = "mech_scout"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"
SCOUT_CONTENT = b"id: mech_scout\n"

TOKEN = "rafa-token"
RAFA = "auth|rafa"

OK = 200
WITHHELD = 503

SLOW_S = 1.0
"""What "within its normal response time" means for a handler returning a dict."""

COMPLETE = {
    "CANON_PROJECT": "ironwood",
    "CANON_REPOSITORY_URL": "git@github.com:cyberdynecorp/ironwood.git",
    "CANON_REPOSITORY_BRANCH": "canon",
    "CANON_REPOSITORY_CREDENTIAL": "a-deploy-key",
    "CANON_FETCH_INTERVAL_S": "300",
    "CANON_WEBHOOK_SECRET": "a-webhook-secret",
    "CANON_AUTH_ISSUER": "https://auth.cyberdynecorp.ai/",
    "CANON_AUTH_AUDIENCE": "cybercanon",
    "CANON_AUTH_CLIENT_ID": "cyb_Complete0Client1",
    "CANON_AUTH_ORG_ID": "org_Complete0Studio",
    "CANON_AUTH_KEY_SET_URL": "https://auth.cyberdynecorp.ai/.well-known/jwks.json",
    "CANON_AUTH_GROUP_ROLES": "art-leads=ART_DIRECTOR,artists=ARTIST",
    "CANON_DATABASE_URL": "postgresql://canon@db/canon",
    "CANON_OBJECT_STORE_URL": "https://minio.cyberdynecorp.ai",
    "CANON_LINK_EXPIRY_S": "120",
    "CANON_WRITE_BACK_TIMEOUT_S": "30",
    "CANON_DRAIN_WINDOW_S": "90",
}
"""A configured deployment. Every scenario below starts from this and breaks one thing."""

DEPLOY_README = Path("deploy") / "README.md"

SECRET_VALUE = "postgres-password-hunter2"
"""A malformed secret: no scheme, so it cannot be read as a connection string."""

API_IMAGE = Path("deploy") / "api.Dockerfile"
SCAN_SUITE = Path("tests") / "tooling" / "test_secret_scan.py"
MIGRATIONS = Path("db") / "migrations"
BROKEN = "0999_broken.sql"
"""A migration file the database refuses, numbered last so the rest applies."""

MULE_SPEC = "vehicles/mule/asset.yaml"

CORPUS: dict[str, bytes] = {
    ".canon/project.yaml": b"schema_version: 1\nname: cyberdyne-game\n",
    SCOUT_SPEC: b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n",
    MULE_SPEC: b"schema_version: 1\nid: mule\nname: Mule Hauler\nstatus: concept\n",
}
"""What a real working copy holds when a scenario needs one: two assets, on disk."""


@pytest.fixture
def deployment() -> dict[str, Any]:
    """What this scenario configured, started, and asked."""
    return {}


# --------------------------------------------------------------------------
# One deployed API, in memory
# --------------------------------------------------------------------------


@dataclass
class Deployed:
    """The application under test, its wiring and the fakes behind it."""

    client: TestClient
    surface: Surface
    fakes: dict[str, Any]

    @property
    def journal(self) -> DeploymentJournal:
        return self.surface.journal

    @property
    def host(self) -> Any:
        return self.fakes["repository_host"]

    def get(self, path: str, token: str = "") -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(path, headers=headers)


def _an_asset(asset_id: str = SCOUT) -> Asset:
    return Asset(
        id=AssetId(asset_id),
        name=asset_id.replace("_", " ").title(),
        constraints=Constraints(naming="SM_{asset}_LOD{n}"),
    )


def _a_person(project: str = PROJECT) -> Actor:
    return Actor(
        id=ActorId(RAFA),
        display_name="Rafa",
        roles=(Role.ART_DIRECTOR,),
        projects=(PROJECT, OTHER_PROJECT),
    )


def a_deployment(
    *,
    dependencies: tuple[Any, ...] = (),
    projects: tuple[str, ...] = (PROJECT,),
) -> Deployed:
    """One API instance serving the named projects, reaching nothing real."""
    fakes = build_fakes()
    store, index, host = fakes["spec_store"], fakes["search_index"], fakes["repository_host"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SCOUT_SPEC, _an_asset())
    index.upsert(
        IndexedAsset(asset_id=SCOUT, name="Mech Scout", spec_path=SCOUT_SPEC, project=PROJECT)
    )
    fakes["identity_provider"].add(Credential(TOKEN), _a_person())

    container = Container(
        spec_store=store,
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=fakes["blob_store"],
        search_index=index,
    )
    hosted = {}
    for name in projects:
        host.add_project(name, {SCOUT_SPEC: SCOUT_CONTENT})
        host.clone(name)
        hosted[name] = HostedProject(name=name, container=container, repository_host=host)
    store.snapshot(host.head(PROJECT).value)

    surface = Surface(
        projects=hosted,
        identity_provider=fakes["identity_provider"],
        observe=lambda: dependencies,
    )
    return Deployed(client=TestClient(build_app(surface=surface)), surface=surface, fakes=fakes)


def _started(deployment: dict[str, Any]) -> None:
    """Start the service with whatever environment the scenario configured."""
    try:
        deployment["application"] = application(deployment["environment"])
    except ConfigurationRejected as refused:
        deployment["refusal"] = refused


def _status_of(deployment: dict[str, Any]) -> dict[str, Any]:
    return deployment["deployed"].get(STATUS_PATH, token=TOKEN).json()["data"]


def _project_in(reported: dict[str, Any], project: str) -> dict[str, Any]:
    return next(one for one in reported[PROJECTS_FIELD] if one["project"] == project)


def _source(repo_root: Path, path: Path) -> str:
    return (repo_root / path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A configuration file is not consulted",
)
def test_a_configuration_file_is_not_consulted() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Changing a setting requires no new artifact",
)
def test_changing_a_setting_requires_no_new_artifact() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Missing setting names itself",
)
def test_missing_setting_names_itself() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Malformed value is refused at boot, not at first request",
)
def test_malformed_value_is_refused_at_boot() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Optional configuration absent is not a startup failure",
)
def test_optional_configuration_absent_is_not_a_startup_failure() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Secret values are not echoed",
)
def test_secret_values_are_not_echoed() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Live but not ready during warm-up",
)
def test_live_but_not_ready_during_warm_up() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Liveness performs no dependency access",
)
def test_liveness_performs_no_dependency_access() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Not ready withholds traffic instead of restarting",
)
def test_not_ready_withholds_traffic_instead_of_restarting() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Model gateway outage does not block a deploy",
)
def test_model_gateway_outage_does_not_block_a_deploy() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Identity provider outage does not block a deploy",
)
def test_identity_provider_outage_does_not_block_a_deploy() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A lost working copy does withhold traffic",
)
def test_a_lost_working_copy_does_withhold_traffic() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A lost index does NOT withhold traffic",
)
def test_a_lost_index_does_not_withhold_traffic() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Stale index is visible as stale",
)
def test_stale_index_is_visible_as_stale() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A silently failing fetch is detectable",
)
def test_a_silently_failing_fetch_is_detectable() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Freshness is answerable per project",
)
def test_freshness_is_answerable_per_project() -> None: ...


# --------------------------------------------------------------------------
# Configuration comes only from the environment
# --------------------------------------------------------------------------


@given("a required setting is absent from the environment")
def _one_setting_absent(deployment: dict[str, Any]) -> None:
    deployment["absent"] = ("CANON_DATABASE_URL",)
    deployment["environment"] = {
        name: value for name, value in COMPLETE.items() if name not in deployment["absent"]
    }


@given("a file containing a value for that setting is present in the image and on a mounted volume")
def _a_file_holds_it(deployment: dict[str, Any], tmp_path: Path) -> None:
    """Both places somebody would put one, both readable, both irrelevant."""
    for place in ("image/.env", "mnt/config/settings.env"):
        written = tmp_path / place
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(
            "\n".join(f"{name}={value}" for name, value in COMPLETE.items()), encoding="utf-8"
        )
    deployment["files"] = tmp_path


@given("a running deployment")
def _a_running_deployment(deployment: dict[str, Any], repo_root: Path) -> None:
    deployment["environment"] = dict(COMPLETE)
    deployment["configuration"] = configuration.load(deployment["environment"])
    deployment["artifact"] = _artifact_digest(repo_root)


@given("two required settings are absent from the environment")
def _two_settings_absent(deployment: dict[str, Any]) -> None:
    deployment["absent"] = ("CANON_AUTH_ISSUER", "CANON_WEBHOOK_SECRET")
    deployment["environment"] = {
        name: value for name, value in COMPLETE.items() if name not in deployment["absent"]
    }


@given("a required setting whose value cannot be interpreted as the type it declares")
def _a_malformed_setting(deployment: dict[str, Any]) -> None:
    deployment["malformed"] = "CANON_FETCH_INTERVAL_S"
    deployment["environment"] = {**COMPLETE, "CANON_FETCH_INTERVAL_S": "every five minutes"}


@given("the language model configuration is absent and the master switch is off")
def _no_model_configured(deployment: dict[str, Any]) -> None:
    deployment["environment"] = dict(COMPLETE)
    assert not any(name.startswith("CANON_LLM") for name in deployment["environment"])


@given("a required secret setting is present but malformed")
def _a_malformed_secret(deployment: dict[str, Any]) -> None:
    deployment["malformed"] = "CANON_DATABASE_URL"
    deployment["secret"] = SECRET_VALUE
    deployment["environment"] = {**COMPLETE, "CANON_DATABASE_URL": SECRET_VALUE}
    assert deployment["malformed"] in configuration.SECRETS


@when("the service starts")
def _the_service_starts(deployment: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Start it, recording what it did, and count the applications it built."""
    built: list[Any] = []
    real = main.build_app
    monkeypatch.setattr(main, "build_app", lambda *a, **k: built.append(a) or real(*a, **k))
    deployment["built"] = built
    _started(deployment)


@when("startup fails")
def _startup_fails(deployment: dict[str, Any]) -> None:
    _started(deployment)
    assert "refusal" in deployment


@when("an environment value is changed and the service is restarted")
def _a_value_is_changed(deployment: dict[str, Any]) -> None:
    deployment["environment"] = {**COMPLETE, "CANON_REPOSITORY_BRANCH": "canon-writeback"}
    deployment["configuration"] = configuration.load(deployment["environment"])


@then("it SHALL treat the setting as absent")
def _treated_as_absent(deployment: dict[str, Any]) -> None:
    refusal = deployment["refusal"]

    assert isinstance(refusal, ConfigurationIncomplete)
    assert refusal.missing == deployment["absent"]


@then("the new value SHALL take effect")
def _the_new_value_took_effect(deployment: dict[str, Any]) -> None:
    assert deployment["configuration"].repository.branch == "canon-writeback"


@then("no new deployable artifact SHALL be produced")
def _no_new_artifact(deployment: dict[str, Any], repo_root: Path) -> None:
    assert _artifact_digest(repo_root) == deployment["artifact"]


@then("startup SHALL fail")
def _startup_failed(deployment: dict[str, Any]) -> None:
    assert isinstance(deployment["refusal"], ConfigurationRejected)
    assert "application" not in deployment


@then("the failure message SHALL name both absent settings")
def _both_names_in_one_message(deployment: dict[str, Any]) -> None:
    message = deployment["refusal"].message

    for name in deployment["absent"]:
        assert name in message


@then("startup SHALL fail naming that setting and its expected shape")
def _named_with_its_shape(deployment: dict[str, Any]) -> None:
    refusal = deployment["refusal"]
    expected = next(
        setting.expected
        for setting in configuration.SETTINGS
        if setting.name == deployment["malformed"]
    )

    assert isinstance(refusal, ConfigurationInvalid)
    assert deployment["malformed"] in refusal.message
    assert expected in refusal.message


@then("no request SHALL have been served")
def _nothing_was_served(deployment: dict[str, Any]) -> None:
    """There is no application to serve one: the refusal came first."""
    assert deployment["built"] == []
    assert "application" not in deployment


@then("startup SHALL succeed")
def _startup_succeeded(deployment: dict[str, Any]) -> None:
    assert "refusal" not in deployment
    assert deployment["application"] is not None


@then("the model-dependent features SHALL report themselves unavailable")
def _the_model_is_unavailable(deployment: dict[str, Any]) -> None:
    client = TestClient(deployment["application"])
    body = client.get(READY_PATH).json()
    described = {one["name"]: one for one in body[DEPENDENCIES_FIELD]}

    assert body[STATUS_FIELD] == READY
    assert LANGUAGE_MODEL in body[DEGRADED_FIELD]
    assert described[LANGUAGE_MODEL]["state"] == "unavailable"
    assert configuration.MODEL_ENABLED in described[LANGUAGE_MODEL]["detail"]


@then("the message SHALL name the setting")
def _the_message_names_the_setting(deployment: dict[str, Any]) -> None:
    assert deployment["malformed"] in deployment["refusal"].message


@then("SHALL NOT contain its value")
def _the_message_omits_the_value(deployment: dict[str, Any]) -> None:
    refusal = deployment["refusal"]
    rendered = "".join(traceback.format_exception(type(refusal), refusal, refusal.__traceback__))

    assert deployment["secret"] not in refusal.message
    assert deployment["secret"] not in repr(refusal)
    assert deployment["secret"] not in rendered


def _artifact_digest(repo_root: Path) -> tuple[int, ...]:
    """A stand-in for the image digest: the deployable's own source, unchanged."""
    import hashlib

    paths = sorted((repo_root / "services" / "cybercanon" / "api").glob("*.py"))
    return tuple(int(hashlib.sha256(path.read_bytes()).hexdigest(), 16) for path in paths)


# --------------------------------------------------------------------------
# Liveness, readiness, and what may withhold traffic
# --------------------------------------------------------------------------


@given("a service whose own datastore is not yet reachable")
def _the_working_copy_is_not_there_yet(deployment: dict[str, Any]) -> None:
    """The datastore this service owns is its working copy — git is the truth."""
    deployment["deployed"] = a_deployment(
        dependencies=(unavailable(WORKING_COPY, "still provisioning"),)
    )


@given("every dependency of a service is unreachable")
def _everything_is_unreachable(deployment: dict[str, Any]) -> None:
    def raising() -> Any:
        raise RuntimeError("every dependency of this service is unreachable")

    deployed = a_deployment()
    surface = replace(deployed.surface, observe=raising)
    deployment["deployed"] = Deployed(
        client=TestClient(build_app(surface=surface)), surface=surface, fakes=deployed.fakes
    )


@given("a running instance reporting not ready")
def _an_instance_reporting_not_ready(deployment: dict[str, Any]) -> None:
    deployment["deployed"] = a_deployment(
        dependencies=(unavailable(WORKING_COPY, "volume not mounted"),)
    )


@given("the configured language model endpoint is unreachable")
def _the_model_endpoint_is_unreachable(deployment: dict[str, Any]) -> None:
    deployment["deployed"] = a_deployment(
        dependencies=(
            available(WORKING_COPY),
            unavailable(LANGUAGE_MODEL, "connection refused"),
        )
    )


@given("the identity provider is unreachable")
def _the_identity_provider_is_unreachable(deployment: dict[str, Any]) -> None:
    """Its keys are cached (D8), so an existing token still verifies."""
    deployment["deployed"] = a_deployment(
        dependencies=(
            available(WORKING_COPY),
            unavailable(IDENTITY_SERVICE, "connection refused"),
        )
    )


@given("the API service cannot reach a project's working copy volume")
def _the_working_copy_volume_is_lost(deployment: dict[str, Any]) -> None:
    deployment["deployed"] = a_deployment(
        dependencies=(unavailable(WORKING_COPY, "/data/worktrees: no such file or directory"),)
    )


@given("the API service cannot reach the index database")
def _the_index_is_lost(deployment: dict[str, Any]) -> None:
    deployment["deployed"] = a_deployment(
        dependencies=(available(WORKING_COPY), unavailable(SEARCH_INDEX, "connection refused"))
    )


@when("both signals are read")
def _both_signals_are_read(deployment: dict[str, Any]) -> None:
    deployed = deployment["deployed"]
    deployment["live"] = deployed.get(LIVE_PATH)
    deployment["ready"] = deployed.get(READY_PATH)


@when("the liveness signal is read")
def _the_liveness_signal_is_read(deployment: dict[str, Any]) -> None:
    started = time.monotonic()
    deployment["live"] = deployment["deployed"].get(LIVE_PATH)
    deployment["elapsed"] = time.monotonic() - started


@when("the deployment platform evaluates it")
def _the_platform_evaluates_it(deployment: dict[str, Any], repo_root: Path) -> None:
    """What the platform reads, and what `deploy/README.md` tells it to read."""
    deployed = deployment["deployed"]
    deployment["ready"] = deployed.get(READY_PATH)
    deployment["live"] = deployed.get(LIVE_PATH)
    deployment["operations"] = _source(repo_root, DEPLOY_README)


@when("a new version is deployed and its readiness is evaluated")
def _a_new_version_is_deployed(deployment: dict[str, Any]) -> None:
    deployment["ready"] = deployment["deployed"].get(READY_PATH)
    deployment["deploy_completed"] = deployment["ready"].status_code == OK


@when("readiness is evaluated")
def _readiness_is_evaluated(deployment: dict[str, Any]) -> None:
    deployment["ready"] = deployment["deployed"].get(READY_PATH)


@then("liveness SHALL report responsive")
def _liveness_is_responsive(deployment: dict[str, Any]) -> None:
    response = deployment["live"]

    assert response.status_code == OK
    assert response.json()[STATUS_FIELD] == ALIVE


@then("readiness SHALL report not ready")
def _readiness_is_not_ready(deployment: dict[str, Any]) -> None:
    response = deployment["ready"]

    assert response.status_code == WITHHELD
    assert response.json()[STATUS_FIELD] == NOT_READY


@then("it SHALL answer within its normal response time and report responsive")
def _liveness_answered_quickly(deployment: dict[str, Any]) -> None:
    response = deployment["live"]

    assert response.status_code == OK
    assert response.json()[STATUS_FIELD] == ALIVE
    assert deployment["elapsed"] < SLOW_S


@then("no request SHALL be routed to that instance")
def _no_traffic_is_routed(deployment: dict[str, Any]) -> None:
    """The routing gate reads readiness, and readiness is not answering ready."""
    assert deployment["ready"].status_code == WITHHELD
    assert "readiness gate → `/readyz`" in deployment["operations"]


@then("the instance SHALL NOT be terminated for reporting not ready")
def _the_instance_is_not_restarted(deployment: dict[str, Any]) -> None:
    """Restarting is liveness's business, and liveness is still responsive."""
    assert deployment["live"].status_code == OK
    assert "liveness probe → `/healthz`" in deployment["operations"]
    assert "is not terminated for that reason alone" in deployment["operations"]


@then("readiness SHALL report ready")
def _readiness_is_ready(deployment: dict[str, Any]) -> None:
    response = deployment["ready"]

    assert response.status_code == OK
    assert response.json()[STATUS_FIELD] == READY


@then("the deploy SHALL complete")
def _the_deploy_completed(deployment: dict[str, Any]) -> None:
    assert deployment["deploy_completed"]


@then("the status surface SHALL report the model-dependent features degraded")
def _the_status_surface_reports_the_model_degraded(deployment: dict[str, Any]) -> None:
    assert _status_of(deployment)[DEGRADED_FIELD] == [LANGUAGE_MODEL]


@then("the status surface SHALL name the identity provider as unreachable")
def _the_status_surface_names_the_identity_provider(deployment: dict[str, Any]) -> None:
    reported = _status_of(deployment)
    described = {one["name"]: one for one in reported[DEPENDENCIES_FIELD]}

    assert reported[DEGRADED_FIELD] == [IDENTITY_SERVICE]
    assert described[IDENTITY_SERVICE]["state"] == "unavailable"


@then("readiness SHALL report not ready, naming the working copy")
def _not_ready_naming_the_working_copy(deployment: dict[str, Any]) -> None:
    response = deployment["ready"]
    body = response.json()

    assert response.status_code == WITHHELD
    assert body[STATUS_FIELD] == NOT_READY
    assert body["error"]["subject"] == WORKING_COPY
    assert WORKING_COPY in body["error"]["message"]


@then("the status surface SHALL name the index as unavailable")
def _the_status_surface_names_the_index(deployment: dict[str, Any]) -> None:
    reported = _status_of(deployment)
    described = {one["name"]: one for one in reported[DEPENDENCIES_FIELD]}

    assert reported[DEGRADED_FIELD] == [SEARCH_INDEX]
    assert described[SEARCH_INDEX]["state"] == "unavailable"


@then("answers derivable from the working copy alone SHALL continue to be served")
def _the_working_copy_still_answers(deployment: dict[str, Any]) -> None:
    """The project briefing is compiled from the repository, with no index row."""
    deployed = deployment["deployed"]
    broken = replace(
        deployed.surface.projects[PROJECT],
        container=replace(deployed.surface.projects[PROJECT].container, search_index=None),
    )
    surface = replace(deployed.surface, projects={PROJECT: broken})
    client = TestClient(build_app(surface=surface))

    response = client.get(
        f"/{VERSION}/projects/{PROJECT}/briefing", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == OK


# --------------------------------------------------------------------------
# Freshness on the status surface
# --------------------------------------------------------------------------


@given("the working copy has fetched a newer revision than the one the index was built from")
def _the_index_is_behind(deployment: dict[str, Any]) -> None:
    deployed = a_deployment()
    indexed = deployed.host.head(PROJECT).value
    deployed.journal.built(PROJECT, indexed)
    deployed.host.push_to_remote(PROJECT, SCOUT_SPEC, b"id: mech_scout\nname: Scout\n")
    refresh_and_record(PROJECT, repository_host=deployed.host, journal=deployed.journal)

    deployment["deployed"] = deployed
    deployment["indexed"] = indexed
    deployment["fetched"] = deployed.host.head(PROJECT).value


@given("fetching has failed on every attempt for several scheduled intervals")
def _every_fetch_has_failed(deployment: dict[str, Any]) -> None:
    deployed = a_deployment()
    refresh_and_record(PROJECT, repository_host=deployed.host, journal=deployed.journal)
    deployment["succeeded_at"] = deployed.journal.attempt(PROJECT).at

    deployed.host.fail_next_fetch(PROJECT, times=4)
    for _ in range(4):
        refresh_and_record(PROJECT, repository_host=deployed.host, journal=deployed.journal)
    deployment["deployed"] = deployed


@given("more than one project is configured")
def _two_projects_are_configured(deployment: dict[str, Any]) -> None:
    deployed = a_deployment(projects=(PROJECT, OTHER_PROJECT))
    refresh_and_record(PROJECT, repository_host=deployed.host, journal=deployed.journal)
    deployed.journal.built(PROJECT, deployed.host.head(PROJECT).value)
    deployed.host.push_to_remote(OTHER_PROJECT, SCOUT_SPEC, b"id: other\n")
    deployed.host.fail_next_fetch(OTHER_PROJECT)
    refresh_and_record(OTHER_PROJECT, repository_host=deployed.host, journal=deployed.journal)
    deployment["deployed"] = deployed


@when("the status surface is read")
def _the_status_surface_is_read(deployment: dict[str, Any]) -> None:
    deployment["reported"] = _status_of(deployment)


@then("it SHALL report the index as not matching the working copy")
def _the_index_is_reported_stale(deployment: dict[str, Any]) -> None:
    assert _project_in(deployment["reported"], PROJECT)["index"]["in_sync"] is False


@then("SHALL name both revisions")
def _both_revisions_are_named(deployment: dict[str, Any]) -> None:
    index = _project_in(deployment["reported"], PROJECT)["index"]

    assert index["indexed_revision"] == deployment["indexed"]
    assert index["working_copy_revision"] == deployment["fetched"]
    assert index["indexed_revision"] != index["working_copy_revision"]


@then("the last successful fetch time SHALL be the time before the failures began")
def _the_last_success_did_not_move(deployment: dict[str, Any]) -> None:
    copy = _project_in(deployment["reported"], PROJECT)["working_copy"]

    assert copy["last_fetch_at"] == deployment["succeeded_at"].isoformat()


@then("the most recent attempt SHALL be reported as failed with its time and reason")
def _the_latest_attempt_is_reported_failed(deployment: dict[str, Any]) -> None:
    attempt = _project_in(deployment["reported"], PROJECT)["working_copy"]["last_attempt"]

    assert attempt["outcome"] == "failed"
    assert attempt["reason"]
    assert attempt["at"] > deployment["succeeded_at"].isoformat()


@then("each project SHALL carry its own revision, fetch times and index-match state")
def _each_project_carries_its_own(deployment: dict[str, Any]) -> None:
    reported = deployment["reported"]
    one = _project_in(reported, PROJECT)
    two = _project_in(reported, OTHER_PROJECT)

    assert len(reported[PROJECTS_FIELD]) == 2
    assert one["working_copy"]["revision"] != two["working_copy"]["revision"]
    assert one["working_copy"]["last_attempt"]["outcome"] == "succeeded"
    assert two["working_copy"]["last_attempt"]["outcome"] == "failed"
    assert one["index"]["in_sync"] is True
    assert two["index"]["in_sync"] is False
    assert json.dumps(reported)  # the whole answer is renderable, per project


# ==========================================================================
# Groups 3 to 5 — artifacts, the release step, and the state on the volumes
# ==========================================================================
#
# Eleven more scenarios, and the same rule as above about what a step is allowed
# to drive: the real scanner over the real repository, the real migration runner
# against a real PostgreSQL, the real single-writer lock over a real git working
# copy shared by two instances. Where a scenario's subject is a *process* rather
# than a call — a release that must not start a server, a version that must keep
# serving — the heavier form with real `uvicorn` processes and a real shell
# release command lives in `tests/integration/test_migration_release_step.py`,
# and what is driven here is the same code from inside the run.
#
# Four scenarios of this capability stay **pending on purpose** and are still
# listed in `tests/bdd/pending.txt`: promotion and rollback (a running
# environment's digest is not something a test can read without a platform), and
# the two image-build scenarios (no container engine is assumed on a developer's
# machine — `tests/tooling/test_container_artifacts.py` builds where there is
# one and skips, loudly, where there is not).


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Repository inspection reveals no secret",
)
def test_repository_inspection_reveals_no_secret() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Artifact inspection reveals no secret",
)
def test_artifact_inspection_reveals_no_secret() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Failed migration aborts the release",
)
def test_failed_migration_aborts_the_release() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "The schema version is reportable after a failure",
)
def test_the_schema_version_is_reportable_after_a_failure() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Migrations do not run per instance",
)
def test_migrations_do_not_run_per_instance() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Recovery from a broken schema is a rebuild",
)
def test_recovery_from_a_broken_schema_is_a_rebuild() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Redeploy preserves state",
)
def test_redeploy_preserves_state() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Blobs outlive a restart",
)
def test_blobs_outlive_a_restart() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Degradation during recovery is bounded and visible",
)
def test_degradation_during_recovery_is_bounded_and_visible() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Success is reported only for a landed commit",
)
def test_success_is_reported_only_for_a_landed_commit() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Only one write-back touches a project's working copy at a time",
)
def test_only_one_write_back_touches_a_working_copy_at_a_time() -> None: ...


# --------------------------------------------------------------------------
# No secret in the repository, and none in an artifact
# --------------------------------------------------------------------------


@when("the repository is scanned for credentials at any revision reachable from the default branch")
def _the_repository_is_scanned(deployment: dict[str, Any], repo_root: Path) -> None:
    deployment["found"] = secrets.scan_repository(repo_root)
    deployment["blobs"] = len(list(secrets.history_blobs(repo_root)))


@given("a deployable artifact for any hosted service")
def _a_deployable_artifact(deployment: dict[str, Any], repo_root: Path) -> None:
    deployment["artifact"] = repo_root / API_IMAGE
    assert deployment["artifact"].is_file()


@when("its contents are searched for the values of the declared secret settings")
def _the_artifact_is_searched(deployment: dict[str, Any], repo_root: Path) -> None:
    configured = [f"the-configured-{name.lower()}" for name in configuration.SECRETS]
    deployment["found"] = secrets.scan_artifact(repo_root, deployment["artifact"], configured)
    deployment["searched_for"] = configured


@then("none SHALL be found")
def _no_credential_was_found(deployment: dict[str, Any]) -> None:
    found = deployment["found"]

    assert found == (), "\n".join(str(one) for one in found)
    assert deployment.get("blobs", 1) > 0, "the scan read no revision at all"
    assert deployment.get("searched_for", ["x"]), "the scan searched for nothing"


@then("the scan SHALL be part of the automated checks that gate a merge")
def _the_scan_gates_a_merge(recipes: dict[str, Any], repo_root: Path) -> None:
    """`just check` is the merge gate, and the scan is a test that recipe runs."""
    assert (repo_root / SCAN_SUITE).is_file()
    assert "test" in recipes["check"].dependencies


# --------------------------------------------------------------------------
# The release step, and what a failed one leaves behind
# --------------------------------------------------------------------------


def _fresh_database(server: Any, name: str) -> str:
    """An empty database — no schema, not even the ledger."""
    server.psql(f"DROP DATABASE IF EXISTS {name}")
    server.psql(f"CREATE DATABASE {name}")
    return server.get_uri(database=name)


def _broken_migration_set(tmp_path: Path, repo_root: Path) -> Path:
    """The real migration set, with one file the database will refuse, last."""
    directory = tmp_path / "migrations"
    shutil.copytree(repo_root / MIGRATIONS, directory)
    (directory / BROKEN).write_text("CREATE TABLE assets (this is not sql);", encoding="utf-8")
    return directory


def _tables_of(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _release(deployment: dict[str, Any]) -> None:
    """Run the release step, and start the new version only if it succeeded.

    That `only if` is the platform's pre-deploy command wired with `&&`, and
    `tests/integration/test_migration_release_step.py` runs exactly this
    sequence as a real shell command against a real `uvicorn`, which is where
    *"no instance of the new version served a request"* is asserted against a
    socket rather than against an object.
    """
    environment = {**COMPLETE, "CANON_DATABASE_URL": deployment["dsn"]}
    deployment["exit_code"] = migrate.main([str(deployment["migrations"])], environment)
    deployment["new_instance"] = a_deployment() if deployment["exit_code"] == 0 else None


@given("a release whose migration fails")
def _a_release_whose_migration_fails(
    deployment: dict[str, Any], tmp_path: Path, repo_root: Path, postgres_server: Any
) -> None:
    deployment["dsn"] = _fresh_database(postgres_server, "bdd_release")
    deployment["migrations"] = _broken_migration_set(tmp_path, repo_root)
    deployment["previous"] = a_deployment()
    assert deployment["previous"].get(LIVE_PATH).status_code == OK


@when("the release step completes")
def _the_release_step_completes(deployment: dict[str, Any]) -> None:
    _release(deployment)


@then("it SHALL report failure")
def _the_release_step_reported_failure(deployment: dict[str, Any]) -> None:
    assert deployment["exit_code"] != 0


@then("no instance of the new version SHALL have served a request")
def _no_new_instance_served(deployment: dict[str, Any]) -> None:
    assert deployment["new_instance"] is None


@then("the previously deployed version SHALL still be serving")
def _the_previous_version_still_serves(deployment: dict[str, Any]) -> None:
    previous = deployment["previous"]

    assert previous.get(LIVE_PATH).json()[STATUS_FIELD] == ALIVE
    assert previous.get(READY_PATH).json()[STATUS_FIELD] == READY


@given("a migration failed partway through a release")
def _a_migration_failed_partway(
    deployment: dict[str, Any], tmp_path: Path, repo_root: Path, postgres_server: Any
) -> None:
    deployment["dsn"] = _fresh_database(postgres_server, "bdd_partway")
    deployment["migrations"] = _broken_migration_set(tmp_path, repo_root)
    deployment["environment"] = {**COMPLETE, "CANON_DATABASE_URL": deployment["dsn"]}
    assert migrate.main([str(deployment["migrations"])], deployment["environment"]) != 0


@when("the schema version is queried")
def _the_schema_version_is_queried(deployment: dict[str, Any]) -> None:
    deployment["schema_version"] = migrate.version(deployment["environment"])


@then("it SHALL report a recorded version")
def _a_version_is_reported(deployment: dict[str, Any]) -> None:
    assert deployment["schema_version"]


@then("that version SHALL identify which migrations have been applied")
def _the_version_identifies_what_applied(deployment: dict[str, Any], repo_root: Path) -> None:
    every = [one.version for one in migrations.migrations_in(repo_root / MIGRATIONS)]
    with psycopg.connect(deployment["dsn"]) as connection:
        applied = migrations.applied_versions(connection)

    assert deployment["schema_version"] == every[-1] == max(applied)
    assert applied == frozenset(every), "the version names the set that landed"


@given("a release that starts more than one instance")
def _a_release_starting_two_instances(deployment: dict[str, Any], postgres_server: Any) -> None:
    deployment["dsn"] = _fresh_database(postgres_server, "bdd_instances")
    deployment["environment"] = {**COMPLETE, "CANON_DATABASE_URL": deployment["dsn"]}


@when("the instances start")
def _the_instances_start(deployment: dict[str, Any]) -> None:
    deployment["instances"] = [application(deployment["environment"]) for _ in range(2)]
    for instance in deployment["instances"]:
        with TestClient(instance) as client:
            assert client.get(LIVE_PATH).json()[STATUS_FIELD] == ALIVE


@then("no instance SHALL attempt a migration")
def _no_instance_migrated(deployment: dict[str, Any]) -> None:
    assert len(deployment["instances"]) == 2
    assert _tables_of(deployment["dsn"]) == set(), "an instance created the schema at start"


# --------------------------------------------------------------------------
# Recovery is a rebuild, and there is no backup to restore from
# --------------------------------------------------------------------------


def _a_working_copy(tmp_path: Path, files: dict[str, bytes] | None = None) -> Any:
    """A real bare remote holding two assets, and a host serving a copy of it."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    environment = {"HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null"}
    run = partial(commands.run, environment=environment)
    run(None, ["init", "--quiet", "--bare", "--initial-branch=main", str(bare)])
    run(None, ["clone", "--quiet", str(bare), str(seed)])
    for path, content in (CORPUS if files is None else files).items():
        (seed / path).parent.mkdir(parents=True, exist_ok=True)
        (seed / path).write_bytes(content)
    run(seed, ["add", "--all"])
    run(
        seed,
        ["-c", "user.name=Seed", "-c", "user.email=seed@example.com", "commit", "-qm", "seed"],
    )
    run(seed, ["push", "--quiet", "origin", "HEAD:refs/heads/main"])
    host = GitRepositoryHost(
        tmp_path / "working-copies",
        [ProjectRemote(project=PROJECT, url=str(bare), branch="main")],
        environment=environment,
    )
    host.clone(PROJECT)
    return host


def _listing(dsn: str) -> tuple[Any, ...]:
    """Every row the index answers with, without the on-disk fingerprint."""
    with PostgresSearchIndex(dsn) as index:
        return tuple(
            replace(entry, fingerprint=None) for entry in index.list_assets(project=PROJECT)
        )


@given("a schema left in a state no migration can advance")
def _a_schema_no_migration_can_advance(
    deployment: dict[str, Any], tmp_path: Path, postgres_dsn: str
) -> None:
    host = _a_working_copy(tmp_path)
    deployment["host"] = host
    deployment["dsn"] = postgres_dsn
    recover.rebuild_from(host.path(PROJECT), dsn=postgres_dsn)
    deployment["before"] = _listing(postgres_dsn)
    assert deployment["before"], "the project has an index to lose"

    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        connection.execute("DROP TABLE assets CASCADE")
        assert migrations.recorded_version(connection), "the ledger still claims it is current"
    assert migrations.apply_migrations(postgres_dsn).applied == (), "no migration can advance it"


@when("the documented recovery is performed")
def _the_documented_recovery_is_performed(deployment: dict[str, Any]) -> None:
    deployment["recovery"] = recover.recover(
        [deployment["host"].path(PROJECT)], dsn=deployment["dsn"]
    )


@then(
    "the index SHALL be discarded, recreated at the target schema version and rebuilt from the "
    "working copies"
)
def _the_index_was_discarded_and_rebuilt(deployment: dict[str, Any], repo_root: Path) -> None:
    report = deployment["recovery"]
    every = tuple(one.version for one in migrations.migrations_in(repo_root / MIGRATIONS))

    assert set(report.dropped) >= {"assets", migrations.LEDGER_TABLE}
    assert report.applied == every, "recreated at the target version, not patched"
    assert _listing(deployment["dsn"]) == deployment["before"]
    assert report.indexed == len(deployment["before"])


@then("the recovery SHALL NOT require a database backup")
def _the_recovery_used_no_backup(deployment: dict[str, Any]) -> None:
    """There was nothing to restore from, and the procedure never looks for one.

    The database had been dropped and never dumped, so what came back was read
    from the working copy — and the recovery's own code contains no call that
    could have read a backup, which is what keeps the claim true next year.
    """
    source = Path(recover.__file__).read_text(encoding="utf-8").lower()

    assert "pg_dump" not in source and "pg_restore" not in source
    assert "restore(" not in source and "copy from" not in source
    assert deployment["recovery"].rebuilt, "the index came back from the working copy"


# --------------------------------------------------------------------------
# The state on the volumes, and what a restart does to it
# --------------------------------------------------------------------------

SENTINEL = "a_row_no_rebuild_would_keep"


@given("an index built from a known revision and a working copy at that revision")
def _an_index_built_from_a_known_revision(
    deployment: dict[str, Any], tmp_path: Path, postgres_dsn: str
) -> None:
    host = _a_working_copy(tmp_path)
    recover.rebuild_from(host.path(PROJECT), dsn=postgres_dsn)
    with PostgresSearchIndex(postgres_dsn) as index:
        index.upsert(
            IndexedAsset(
                asset_id=SENTINEL,
                name="Written by hand",
                project=PROJECT,
                spec_path="nowhere/asset.yaml",
                directory="nowhere",
            )
        )
    deployment["host"] = host
    deployment["dsn"] = postgres_dsn
    deployment["revision"] = host.head(PROJECT).value
    deployment["before"] = _listing(postgres_dsn)
    deployment["remote"] = host.remote_of(PROJECT)


@when("a new artifact is deployed and the services restart")
def _a_new_artifact_is_deployed(deployment: dict[str, Any]) -> None:
    """A redeploy replaces the process; the volumes are the same ones."""
    host = GitRepositoryHost(
        deployment["host"].root,
        [deployment["remote"]],
        environment={"GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    host.clone(PROJECT)
    deployment["restarted"] = host
    deployment["after"] = _listing(deployment["dsn"])


@then("the index SHALL still be built from that revision")
def _the_index_is_still_the_one_that_was_built(deployment: dict[str, Any]) -> None:
    assert deployment["after"] == deployment["before"]


@then("the working copy SHALL still be at it")
def _the_working_copy_is_still_there(deployment: dict[str, Any]) -> None:
    assert deployment["restarted"].head(PROJECT).value == deployment["revision"]


@then("no rebuild SHALL have been triggered")
def _no_rebuild_was_triggered(deployment: dict[str, Any]) -> None:
    """A rebuild scans the working copy, so it would have dropped this row."""
    with PostgresSearchIndex(deployment["dsn"]) as index:
        assert index.get(SENTINEL, PROJECT) is not None


@given("a preview stored in the blob store")
def _a_preview_stored_in_the_blob_store(deployment: dict[str, Any], tmp_path: Path) -> None:
    volume = tmp_path / "blobs"
    stored = FsBlobStore(volume).put(b"glTF\x02\x00\x00\x00a decimated preview")
    deployment["volume"] = volume
    deployment["key"] = stored.key
    deployment["content"] = FsBlobStore(volume).verified(stored.key)


@when("every service is restarted")
def _every_service_is_restarted(deployment: dict[str, Any]) -> None:
    """The process is replaced; the volume it mounted is not."""
    deployment["restarted_store"] = FsBlobStore(deployment["volume"])


@then("that preview SHALL still be retrievable by the same reference")
def _the_preview_is_still_retrievable(deployment: dict[str, Any]) -> None:
    store = deployment["restarted_store"]

    assert store.exists(deployment["key"])
    assert store.verified(deployment["key"]) == deployment["content"]


@given("an index rebuild is in progress")
def _an_index_rebuild_is_in_progress(deployment: dict[str, Any]) -> None:
    deployed = a_deployment()
    deployed.journal.building(PROJECT)
    deployment["deployed"] = deployed


@then("it SHALL report the rebuild as in progress")
def _the_rebuild_is_reported(deployment: dict[str, Any]) -> None:
    assert _project_in(deployment["reported"], PROJECT)["index"]["rebuilding"] is True


@then(
    "reads that cannot be served from the partial index SHALL report unavailability rather than "
    "an incomplete answer"
)
def _partial_reads_report_unavailability(deployment: dict[str, Any]) -> None:
    deployed = deployment["deployed"]

    listing = deployed.get(f"/{VERSION}/projects/{PROJECT}/assets", token=TOKEN)
    specification = deployed.get(f"/{VERSION}/projects/{PROJECT}/assets/{SCOUT}", token=TOKEN)

    assert listing.status_code == WITHHELD
    assert listing.json()["error"]["id"] == INDEX_REBUILDING
    assert specification.status_code == OK, "the working copy still answers what it can"


# --------------------------------------------------------------------------
# A write-back lands as a commit, or it is reported as nothing
# --------------------------------------------------------------------------


@given("a write-back whose commit could not be pushed to the configured branch")
def _a_write_back_that_cannot_be_pushed(deployment: dict[str, Any]) -> None:
    deployed = a_deployment()
    deployed.host.make_unreachable(PROJECT, "the remote could not be reached")
    deployment["deployed"] = deployed
    deployment["outcome"] = write_back(
        PROJECT,
        [
            Edit(
                path=SCOUT_SPEC,
                content=b"id: mech_scout\nname: Scout\n",
                based_on=ContentHash.of(SCOUT_CONTENT),
            )
        ],
        repository_host=deployed.host,
        author=GitAuthor(name="Rafa", email="rafa@cyberdyne.com"),
        message="mech_scout: set status",
    )


@when("the caller receives its response")
def _the_caller_receives_its_response(deployment: dict[str, Any]) -> None:
    deployment["response"] = deployment["outcome"]


@then("the response SHALL report failure")
def _the_response_reports_failure(deployment: dict[str, Any]) -> None:
    assert not succeeded(deployment["response"])


@then("SHALL state that no change was recorded")
def _the_response_states_nothing_was_recorded(deployment: dict[str, Any]) -> None:
    """The sentence itself; that the *working copy* also holds nothing is the
    next scenario's claim, asserted against real git in
    `tests/integration/test_persistent_state.py`."""
    assert NOTHING_RECORDED in deployment["response"].message


@given(
    "two write-backs for the same project arrive while both an old and a new instance are running"
)
def _two_write_backs_arrive_during_a_rollover(deployment: dict[str, Any], tmp_path: Path) -> None:
    old = _a_working_copy(tmp_path)
    new = GitRepositoryHost(
        old.root,
        [old.remote_of(PROJECT)],
        environment={"GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    new.clone(PROJECT)
    deployment["instances"] = (old, new)
    deployment["edits"] = (
        (SCOUT_SPEC, b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"),
        (MULE_SPEC, b"schema_version: 1\nid: mule\nname: Mule Hauler\nstatus: modeling\n"),
    )


@when("they are processed")
def _the_two_write_backs_are_processed(deployment: dict[str, Any]) -> None:
    instances = deployment["instances"]
    outcomes: list[Any] = [None, None]
    barrier = threading.Barrier(2)

    def submit(index: int) -> None:
        path, content = deployment["edits"][index]
        barrier.wait()
        outcomes[index] = write_back(
            PROJECT,
            [Edit(path=path, content=content, based_on=ContentHash.of(CORPUS[path]))],
            repository_host=instances[index],
            author=GitAuthor(name=f"Writer {index}", email=f"writer{index}@cyberdyne.com"),
            message=f"{path}: written by instance {index}",
        )

    threads = [threading.Thread(target=submit, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    deployment["outcomes"] = outcomes


@then("they SHALL be applied one after the other")
def _they_were_applied_one_after_the_other(deployment: dict[str, Any]) -> None:
    old, new = deployment["instances"]

    assert all(succeeded(outcome) for outcome in deployment["outcomes"])
    assert old.unpushed(PROJECT) == () and new.unpushed(PROJECT) == ()


@then("each SHALL produce its own commit, with neither overwriting the other's change")
def _each_produced_its_own_commit(deployment: dict[str, Any]) -> None:
    new = deployment["instances"][1]
    landed = {outcome.value.commit.revision.value for outcome in deployment["outcomes"]}

    assert len(landed) == 2, "two write-backs, two commits"
    new.fetch(PROJECT, confirmed_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC))
    head = new.head(PROJECT)
    for path, content in deployment["edits"]:
        assert new.read(PROJECT, path, head) == content


# --------------------------------------------------------------------------
# Group 6 — the deploy overlap, and the write-back caught in the middle
#
# The instances here are in-process, exactly as the release-step scenarios
# above are: `tests/integration/test_rollover.py` runs the same four steps
# against two real `uvicorn` processes, which is where "every request received
# a response" is asserted against a socket rather than against an object. The
# properties that are *this* code's rather than the platform's — the drain
# window outliving the write-back budget, an abandoned write-back leaving
# nothing, a commit landing inside the window attributed to its author — are
# asserted here against real git.
# --------------------------------------------------------------------------

VIEW = "characters/mech_scout/concept/front.png"
VIEW_BYTES = b"\x89PNG\r\n\x1a\nthe scout mech, front elevation"

ILLUSTRATED: dict[str, bytes] = {
    ".canon/project.yaml": b"schema_version: 1\nname: cyberdyne-game\n",
    SCOUT_SPEC: (
        b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"
        b"concept:\n  views:\n    - " + VIEW.encode() + b"\n"
    ),
    VIEW: VIEW_BYTES,
}
"""A corpus whose specification points at a file, so a blob mirror has work to do."""

HALF_WRITTEN = b"schema_version: 1\nid: mech_sc"

RAFA_GIT = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")

READS_PER_PHASE = 5
"""How many reads the caller issues in each phase of the rollover."""


def _rollover() -> Any:
    """The configured pair, read from the environment a deployment starts with."""
    return configuration.load(COMPLETE).rollover


def _successor(host: Any) -> Any:
    """The new version, mounting the same working-copy volume (D6, D7)."""
    successor = GitRepositoryHost(
        host.root,
        [host.remote_of(PROJECT)],
        environment={"GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    successor.clone(PROJECT)
    return successor


def _read(deployment: dict[str, Any], route: list[Any]) -> None:
    """One read against whichever instance the routing gate points at."""
    try:
        deployment["answers"].append(route[-1].get(LIVE_PATH).status_code)
    except Exception as dropped:
        deployment["failures"].append(str(dropped))


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Continuous availability across a deploy",
)
def test_continuous_availability_across_a_deploy() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A retiring instance drains before terminating",
)
def test_a_retiring_instance_drains_before_terminating() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A never-ready new version does not replace the old one",
)
def test_a_never_ready_new_version_does_not_replace_the_old_one() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Abandoned write-back leaves no partial edit",
)
def test_abandoned_write_back_leaves_no_partial_edit() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Write-back completes within the drain window",
)
def test_write_back_completes_within_the_drain_window() -> None: ...


@given("a caller issuing read requests continuously")
def _a_caller_reading_continuously(deployment: dict[str, Any]) -> None:
    deployment["previous"] = a_deployment()
    deployment["answers"] = []
    deployment["failures"] = []


@when("a new version is deployed and the previous version is retired")
def _a_new_version_is_deployed(deployment: dict[str, Any]) -> None:
    """The gate's four steps: start, wait for ready, route, then retire."""
    previous = deployment["previous"]
    route = [previous]
    for _ in range(READS_PER_PHASE):
        _read(deployment, route)

    incoming = a_deployment()
    for _ in range(READS_PER_PHASE):
        _read(deployment, route)
    assert incoming.get(READY_PATH).status_code == OK, "it was routed to before it was ready"
    route.append(incoming)

    for _ in range(READS_PER_PHASE):
        _read(deployment, route)
    previous.client.close()
    for _ in range(READS_PER_PHASE):
        _read(deployment, route)
    deployment["retired"] = previous


@then("every request SHALL receive a response")
def _every_request_was_answered(deployment: dict[str, Any]) -> None:
    assert len(deployment["answers"]) == READS_PER_PHASE * 4
    assert deployment["failures"] == []


@then("none SHALL fail because of the rollover")
def _none_failed_because_of_the_rollover(deployment: dict[str, Any]) -> None:
    assert set(deployment["answers"]) == {OK}


@given("an instance with requests in flight is selected for retirement")
def _an_instance_with_requests_in_flight(deployment: dict[str, Any]) -> None:
    """One accepted write-back, not yet finished, on the instance being retired."""
    retiring = a_deployment()
    deployment["retiring"] = retiring
    deployment["successor"] = a_deployment()
    deployment["route"] = [retiring]
    deployment["answers"] = []
    deployment["failures"] = []
    deployment["in_flight"] = Edit(
        path=SCOUT_SPEC,
        content=b"id: mech_scout\nname: Scout\n",
        based_on=ContentHash.of(SCOUT_CONTENT),
    )


@when("retirement begins")
def _retirement_begins(deployment: dict[str, Any]) -> None:
    """New requests go to the successor; the accepted one is given the window."""
    deployment["route"].append(deployment["successor"])
    started = time.monotonic()
    deployment["outcome"] = write_back(
        PROJECT,
        [deployment["in_flight"]],
        repository_host=deployment["retiring"].host,
        author=RAFA_GIT,
        message="mech_scout: set status",
        timeout=_rollover().write_back_timeout,
    )
    deployment["elapsed"] = timedelta(seconds=time.monotonic() - started)
    for _ in range(READS_PER_PHASE):
        _read(deployment, deployment["route"])
    deployment["retiring"].client.close()


@then("it SHALL stop accepting new requests")
def _it_stopped_accepting_new_requests(deployment: dict[str, Any]) -> None:
    """Every request issued after retirement began reached the successor."""
    assert deployment["route"][-1] is deployment["successor"]
    assert deployment["answers"] == [OK] * READS_PER_PHASE
    assert deployment["failures"] == []


@then("SHALL be allowed to complete in-flight requests until a bounded window expires")
def _the_in_flight_request_had_a_bounded_window(deployment: dict[str, Any]) -> None:
    """The bound is two configured numbers in a known order, not a hope (D7)."""
    rollover = _rollover()

    assert rollover.drain_window > rollover.write_back_timeout
    assert succeeded(deployment["outcome"]), "the accepted write-back did not complete"
    assert deployment["elapsed"] < rollover.drain_window


@given("a new version whose readiness never reports ready")
def _a_new_version_that_never_becomes_ready(deployment: dict[str, Any]) -> None:
    """Its own working copy is missing — the one dependency that withholds traffic."""
    deployment["previous"] = a_deployment()
    deployment["incoming"] = a_deployment(
        dependencies=(unavailable(WORKING_COPY, "the volume is not mounted"),)
    )


@when("the deploy times out")
def _the_deploy_times_out(deployment: dict[str, Any]) -> None:
    """The routing gate waited, never saw ready, and routed nothing to it."""
    incoming = deployment["incoming"]
    deployment["became_ready"] = incoming.get(READY_PATH).status_code == OK
    deployment["incoming_alive"] = incoming.get(LIVE_PATH).status_code == OK


@then("the previous version SHALL still be serving traffic")
def _the_previous_version_is_still_serving(deployment: dict[str, Any]) -> None:
    previous = deployment["previous"]

    assert not deployment["became_ready"], "the artifact was supposed never to be ready"
    assert deployment["incoming_alive"], "it is a running instance that is not ready"
    assert previous.get(LIVE_PATH).json()[STATUS_FIELD] == ALIVE
    assert previous.get(READY_PATH).json()[STATUS_FIELD] == READY


@given("a write-back that has modified a specification file but not yet committed")
def _a_write_back_modified_but_not_committed(deployment: dict[str, Any], tmp_path: Path) -> None:
    host = _a_working_copy(tmp_path)
    deployment["host"] = host
    deployment["branch_content"] = CORPUS[SCOUT_SPEC]
    (host.path(PROJECT) / SCOUT_SPEC).write_bytes(HALF_WRITTEN)
    (host.path(PROJECT) / "half-written.yaml").write_bytes(b"and something untracked")


@when("its instance is terminated before the drain window expires")
def _the_instance_is_terminated_mid_write_back(deployment: dict[str, Any]) -> None:
    """The process is gone, so the only thing left is the volume and its successor."""
    successor = _successor(deployment["host"])
    deployment["resumed"] = resume_project(PROJECT, repository_host=successor)
    deployment["successor"] = successor


@then(
    "the working copy SHALL contain no uncommitted modification once the service is running again"
)
def _no_uncommitted_modification_remains(deployment: dict[str, Any]) -> None:
    successor = deployment["successor"]

    assert succeeded(deployment["resumed"])
    assert not (successor.path(PROJECT) / "half-written.yaml").exists()
    assert successor.unpushed(PROJECT) == ()


@then("the specification file SHALL match the configured branch")
def _the_specification_matches_the_branch(deployment: dict[str, Any]) -> None:
    successor = deployment["successor"]
    head = successor.head(PROJECT)

    assert (successor.path(PROJECT) / SCOUT_SPEC).read_bytes() == deployment["branch_content"]
    assert successor.read(PROJECT, SCOUT_SPEC, head) == deployment["branch_content"]


@given("a write-back accepted just before retirement begins")
def _a_write_back_accepted_just_before_retirement(
    deployment: dict[str, Any], tmp_path: Path
) -> None:
    host = _a_working_copy(tmp_path)
    deployment["host"] = host
    deployment["edited"] = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: rigging\n"
    deployment["edit"] = Edit(
        path=SCOUT_SPEC,
        content=deployment["edited"],
        based_on=ContentHash.of(CORPUS[SCOUT_SPEC]),
    )


@when("it commits and pushes within the drain window")
def _it_commits_and_pushes_within_the_window(deployment: dict[str, Any]) -> None:
    started = time.monotonic()
    deployment["outcome"] = write_back(
        PROJECT,
        [deployment["edit"]],
        repository_host=deployment["host"],
        author=RAFA_GIT,
        message="mech_scout: set status",
        timeout=_rollover().write_back_timeout,
    )
    deployment["elapsed"] = timedelta(seconds=time.monotonic() - started)


@then("the caller SHALL receive success")
def _the_caller_received_success(deployment: dict[str, Any]) -> None:
    assert succeeded(deployment["outcome"])
    assert deployment["elapsed"] < _rollover().drain_window


@then("the commit SHALL exist on the configured branch attributed to the acting person")
def _the_commit_is_on_the_branch_attributed(deployment: dict[str, Any]) -> None:
    """Read back through a second instance, so "on the branch" means the remote."""
    successor = _successor(deployment["host"])
    successor.fetch(PROJECT, confirmed_at=datetime(2026, 9, 19, 12, 30, tzinfo=UTC))

    assert successor.read(PROJECT, SCOUT_SPEC, successor.head(PROJECT)) == deployment["edited"]
    assert deployment["host"].unpushed(PROJECT) == ()
    assert deployment["outcome"].value.commit.author == RAFA_GIT


# --------------------------------------------------------------------------
# Group 7 — one volume destroyed at a time, and the procedure that gets it back
#
# `tests/integration/test_recovery_drills.py` is the same three procedures with
# their durations measured and compared against `deploy/recovery.md`; these are
# the scenarios the specification states, over the same real git, real
# PostgreSQL and real blob volume.
# --------------------------------------------------------------------------


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Index volume destroyed",
)
def test_index_volume_destroyed() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Blob volume destroyed",
)
def test_blob_volume_destroyed() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Working copy destroyed",
)
def test_working_copy_destroyed() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Drills are executed, not assumed",
)
def test_drills_are_executed_not_assumed() -> None: ...


RECOVERY_DOCUMENT = Path("deploy") / "recovery.md"

INDEX_TABLES = (
    "assets",
    "search_misses",
    "idempotency_keys",
    "dismissals",
    "schema_migrations",
)


def _mirrored(host: Any, blobs: FsBlobStore) -> dict[str, bytes]:
    """Every blob this project's specifications point at, and its bytes."""
    report = mirror_project(
        PROJECT,
        repository_host=host,
        spec_store=GitSpecStore(host.path(PROJECT)),
        blob_store=blobs,
    )
    assert succeeded(report), report
    return {key: blobs.verified(key) for key in sorted(set(report.value.keys.values()))}


@given("the index volume is deleted while the working copies are intact")
def _the_index_volume_is_deleted(
    deployment: dict[str, Any], tmp_path: Path, postgres_dsn: str
) -> None:
    host = _a_working_copy(tmp_path)
    recover.rebuild_from(host.path(PROJECT), dsn=postgres_dsn)
    deployment["host"] = host
    deployment["dsn"] = postgres_dsn
    deployment["before"] = _listing(postgres_dsn)
    assert deployment["before"], "the project has an index to lose"

    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        for table in INDEX_TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    assert host.path(PROJECT).is_dir(), "one volume at a time: the copy is intact"


@when("the documented index recovery is performed")
def _the_documented_index_recovery_is_performed(deployment: dict[str, Any]) -> None:
    started = time.monotonic()
    deployment["recovery"] = recover.recover(
        [deployment["host"].path(PROJECT)], dsn=deployment["dsn"]
    )
    deployment["elapsed"] = timedelta(seconds=time.monotonic() - started)


@then("lookups SHALL return the same results they returned before the loss")
def _lookups_return_what_they_did_before(deployment: dict[str, Any]) -> None:
    assert _listing(deployment["dsn"]) == deployment["before"]


@then("the elapsed time SHALL be recorded and compared against the stated expected duration")
def _the_elapsed_time_is_compared(deployment: dict[str, Any], repo_root: Path) -> None:
    """The comparison, and the record that makes it possible (D9)."""
    document = (repo_root / RECOVERY_DOCUMENT).read_text(encoding="utf-8")
    stated = {one.procedure: one.expected for one in expectations(document)}

    assert deployment["elapsed"] <= stated["index-rebuild"]
    assert latest(drills(document), "index-rebuild") is not None


@given("the blob volume is deleted while the working copies are intact")
def _the_blob_volume_is_deleted(deployment: dict[str, Any], tmp_path: Path) -> None:
    host = _a_working_copy(tmp_path, ILLUSTRATED)
    volume = tmp_path / "blobs"
    blobs = FsBlobStore(volume)
    deployment["host"] = host
    deployment["volume"] = volume
    deployment["before"] = _mirrored(host, blobs)
    assert deployment["before"], "the project has blobs to lose"

    shutil.rmtree(volume)
    deployment["blobs"] = FsBlobStore(volume)
    assert not any(deployment["blobs"].exists(key) for key in deployment["before"])
    assert host.path(PROJECT).is_dir(), "one volume at a time: the copy is intact"


@when("the documented blob recovery is performed")
def _the_documented_blob_recovery_is_performed(deployment: dict[str, Any]) -> None:
    deployment["after"] = _mirrored(deployment["host"], deployment["blobs"])


@then("every blob derived from repository content SHALL be retrievable again by the same reference")
def _every_blob_is_retrievable_again(deployment: dict[str, Any]) -> None:
    """Keys are content digests, which is what makes *the same reference* sayable."""
    assert deployment["after"] == deployment["before"]
    assert all(deployment["blobs"].exists(key) for key in deployment["before"])


@given("a project's working copy volume is deleted")
def _a_working_copy_volume_is_deleted(
    deployment: dict[str, Any], tmp_path: Path, postgres_dsn: str
) -> None:
    host = _a_working_copy(tmp_path, ILLUSTRATED)
    deployment["host"] = host
    deployment["dsn"] = postgres_dsn
    deployment["volume"] = tmp_path / "blobs"
    deployment["revision"] = host.head(PROJECT).value

    shutil.rmtree(host.path(PROJECT))
    assert not host.path(PROJECT).exists()


@when("the documented working-copy recovery is performed")
def _the_documented_working_copy_recovery_is_performed(deployment: dict[str, Any]) -> None:
    deployment["recovered"] = deployment["host"].recover(PROJECT)


@then("the working copy SHALL be restored at the configured branch's current revision")
def _the_working_copy_is_at_the_branch_revision(deployment: dict[str, Any]) -> None:
    host = deployment["host"]

    assert host.path(PROJECT).is_dir()
    assert host.head(PROJECT).value == deployment["revision"]
    assert host.remote_of(PROJECT).branch == "main"


@then("the index and blob recoveries SHALL be able to run from it")
def _the_other_two_recoveries_run_from_it(deployment: dict[str, Any]) -> None:
    """The order the runbook states: the copy is the only source the others have."""
    host = deployment["host"]
    rebuilt = recover.recover([host.path(PROJECT)], dsn=deployment["dsn"])
    mirrored = _mirrored(host, FsBlobStore(deployment["volume"]))

    assert rebuilt.indexed > 0
    assert _listing(deployment["dsn"])
    assert mirrored


@when("the recovery documentation is inspected")
def _the_recovery_documentation_is_inspected(deployment: dict[str, Any], repo_root: Path) -> None:
    deployment["document"] = (repo_root / RECOVERY_DOCUMENT).read_text(encoding="utf-8")


@then(
    "each of the three procedures SHALL carry the date and measured duration of its most "
    "recent execution"
)
def _each_procedure_carries_its_last_execution(deployment: dict[str, Any]) -> None:
    """*"Drills are executed, not assumed."* The drill writes this, not a person."""
    document = deployment["document"]
    recorded = drills(document)
    stated = {one.procedure: one.expected for one in expectations(document)}

    assert set(stated) == set(PROCEDURES)
    for procedure in PROCEDURES:
        most_recent = latest(recorded, procedure)
        assert most_recent is not None, f"{procedure} has never been drilled"
        assert most_recent.measured > timedelta(0)
        assert most_recent.measured <= stated[procedure]


# --------------------------------------------------------------------------
# Group 8 — the four applications, and the two surfaces that are never hosted
#
# Three of these five scenarios are about a *declaration* and are driven over
# the real one: `deploy/coolify.yaml`, read by `canon_deploy` against this
# specification. An exclusion is the requirement nobody notices breaking —
# nothing fails when a fifth application appears — so the check is the
# mechanism, and the scenario that a deployment exposing the agent surface is
# rejected is executed by fabricating exactly that deployment.
#
# The other two are about *processes* on a developer's machine, and both are
# executed as processes: the agent server answers over standard input and
# output with binding and listening denied in its own interpreter, and `canon
# validate` and an agent lookup both complete with every outbound connection
# raising. Denying it in the child rather than mocking it here is the
# difference between asserting that this code needs no network and asserting
# that this test remembered to mock everything it uses.
#
# `tests/integration/test_component_independence.py` runs the restart matrix
# against a real PostgreSQL, a real S3 API, a real working copy and a real
# `uvicorn` process; what is driven here is the same four components over the
# wired surface, which is where "the other three kept their state" is a
# question about objects rather than about containers.
# --------------------------------------------------------------------------

CRATE = "crate"
CRATE_SPEC = "props/crate/asset.yaml"
CRATE_EXPORT = "props/crate/exports/SM_crate_LOD0.glb"

CRATE_ASSET = """\
schema_version: 1
id: crate
name: Supply Crate
status: modeling
constraints:
  tri_budget: 12000
"""

LOCAL_PROJECT = """\
schema_version: 1
name: Ronin
defaults:
  naming: "SM_{asset}_LOD{n}"
"""

CLEAN = 0
"""What `canon validate` exits with when an export satisfies its specification."""

DENY_NETWORK = '''\
"""Every outbound connection and every name lookup raises in this process."""

import socket


def _denied(*_arguments, **_keywords):
    raise OSError("network access is denied")


socket.socket.connect = _denied
socket.socket.connect_ex = _denied
socket.create_connection = _denied
socket.getaddrinfo = _denied
socket.gethostbyname = _denied
'''

DENY_LISTENING = '''\
"""This process may not become a network server. Binding and listening raise."""

import socket


def _denied(*_arguments, **_keywords):
    raise OSError("this process may not listen on a network port")


socket.socket.bind = _denied
socket.socket.listen = _denied
socket.create_server = _denied
'''


def _a_developer_machine(tmp_path: Path) -> Path:
    """A working copy with one asset and one export, and nothing hosted anywhere."""
    from canon_fixtures import mesh as fixtures

    root = tmp_path / "game"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    for path, text in ((".canon/project.yaml", LOCAL_PROJECT), (CRATE_SPEC, CRATE_ASSET)):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    fixtures.write_static_glb(root / CRATE_EXPORT, name="SM_crate_LOD0")
    return root


def _denying(tmp_path: Path, name: str, source: str) -> dict[str, str]:
    """An environment carrying nothing identifying, and a `sitecustomize` that refuses."""
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sitecustomize.py").write_text(source, encoding="utf-8")
    stripped = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CANON_", "CYBERDYNE_", "OPENAI_", "AWS_", "GIT_"))
        and name not in {"HOME", "USER", "LOGNAME", "SSH_AUTH_SOCK", "GITHUB_TOKEN"}
    }
    return {**stripped, "PYTHONPATH": str(directory)}


def _agent_answers(root: Path, calls: dict[str, dict[str, Any]], env: dict[str, str]):
    """Spawn the agent server and call read tools over standard input and output."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    async def _ask() -> dict[str, str]:
        transport = StdioTransport(
            command=sys.executable,
            args=["-m", "cybercanon.cli", "mcp", "serve", str(root)],
            env=env,
            cwd=str(root),
        )
        async with Client(transport) as client:
            answered = {}
            for tool, payload in calls.items():
                result = await client.call_tool(tool, payload)
                answered[tool] = "\n".join(block.text for block in result.content)
            return answered

    return asyncio.run(_ask())


def _canon(root: Path, *arguments: str, env: dict[str, str]):
    return subprocess.run(
        [sys.executable, "-m", "cybercanon.cli", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _declared(repo_root: Path) -> deployed.Inventory:
    return deployed.load(repo_root / deployed.MANIFEST_PATH)


def _non_conformance(repo_root: Path, inventory: deployed.Inventory) -> tuple[str, ...]:
    return deployed.findings(
        inventory,
        required=configuration.REQUIRED,
        optional=configuration.OPTIONAL,
        web_required=web_variables(repo_root),
    )


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "The inventory is enumerable and complete",
)
def test_the_inventory_is_enumerable_and_complete() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "A component restarts without taking the others down",
)
def test_a_component_restarts_without_taking_the_others_down() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Hosting the agent surface is a specification change",
)
def test_hosting_the_agent_surface_is_a_specification_change() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "No network listener for the agent server",
)
def test_no_network_listener_for_the_agent_server() -> None: ...


@scenario(
    "../features/add-coolify-deployment/deployment-operations.feature",
    "Local tools work with the hosted environment unreachable",
)
def test_local_tools_work_with_the_hosted_environment_unreachable() -> None: ...


# -- the inventory is exactly four -----------------------------------------


@given("a deployed environment")
def _a_deployed_environment(deployment: dict[str, Any], repo_root: Path) -> None:
    deployment["inventory"] = _declared(repo_root)
    deployment["non_conformance"] = _non_conformance(repo_root, deployment["inventory"])


@when("its components are enumerated")
def _its_components_are_enumerated(deployment: dict[str, Any]) -> None:
    deployment["components"] = deployment["inventory"].components


@then(
    "exactly the HTTP API service, the web application, the index database and the blob "
    "store SHALL be present"
)
def _exactly_the_four_are_present(deployment: dict[str, Any]) -> None:
    assert set(deployment["components"]) == set(deployed.COMPONENTS)
    assert len(deployment["components"]) == len(deployed.COMPONENTS)
    assert deployment["non_conformance"] == ()


# -- one of them restarts ---------------------------------------------------


@given("all four components are running")
def _all_four_components_are_running(deployment: dict[str, Any], repo_root: Path) -> None:
    """The four, wired: the API over its index, its blob mirror and its working copy."""
    running = a_deployment(
        dependencies=(
            available(SEARCH_INDEX),
            available(OBJECT_STORE),
            available(WORKING_COPY),
        )
    )
    deployment["deployed"] = running
    deployment["inventory"] = _declared(repo_root)
    deployment["state"] = {
        SEARCH_INDEX: running.fakes["search_index"].get(SCOUT, PROJECT),
        WORKING_COPY: running.host.head(PROJECT).value,
    }
    assert running.get(READY_PATH).json()[STATUS_FIELD] == READY


@when("any one of them is restarted")
def _any_one_of_them_is_restarted(deployment: dict[str, Any]) -> None:
    """Each in turn, because *"any one"* is a claim about all four of them.

    A restart is the component's *process* being replaced while its volume stays
    where it is: the index and the blob mirror go away and come back, and the
    API is rebuilt over the fakes that are its volumes. The web application is
    the fourth, and it depends on none of the others — its own artifact is
    started, stopped and read by `tests/integration/test_web_readiness_process.py`.
    """
    observed: dict[str, Any] = {}
    for component in (SEARCH_INDEX, OBJECT_STORE):
        down = a_deployment(dependencies=(unavailable(component, "restarting"),))
        observed[component] = down.get(READY_PATH).json()
    deployment["during"] = observed

    replaced = a_deployment(
        dependencies=(
            available(SEARCH_INDEX),
            available(OBJECT_STORE),
            available(WORKING_COPY),
        )
    )
    deployment["after"] = replaced
    deployment["recovered"] = {
        SEARCH_INDEX: replaced.fakes["search_index"].get(SCOUT, PROJECT),
        WORKING_COPY: replaced.host.head(PROJECT).value,
    }


@then("the remaining three SHALL continue running")
def _the_remaining_three_continue_running(deployment: dict[str, Any]) -> None:
    """A restart of one is a degraded feature, never a service that stops."""
    for component, answered in deployment["during"].items():
        assert answered[STATUS_FIELD] == READY, f"{component} restarting withheld traffic"
        assert answered[DEGRADED_FIELD] == [component]
    assert deployment["inventory"].by_component(deployed.WEB_APPLICATION).volumes == ()


@then("the restarted component SHALL return to serving without manual intervention")
def _the_restarted_component_returns_to_serving(deployment: dict[str, Any]) -> None:
    after = deployment["after"]

    assert after.get(LIVE_PATH).json()[STATUS_FIELD] == ALIVE
    assert after.get(READY_PATH).json()[DEGRADED_FIELD] == []
    assert deployment["recovered"] == deployment["state"], "state did not survive the restart"


# -- hosting the agent surface is refused -----------------------------------


@given("a request to expose the agent surface over the network")
def _a_request_to_expose_the_agent_surface(deployment: dict[str, Any], repo_root: Path) -> None:
    """The request, granted: a fifth application, with a host, serving it."""
    inventory = _declared(repo_root)
    deployment["inventory"] = replace(
        inventory,
        applications=(
            *inventory.applications,
            deployed.Application(
                name="mcp",
                component=deployed.AGENT_SERVER,
                host=f"mcp.{inventory.host_suffix}",
                dockerfile="deploy/mcp.Dockerfile",
            ),
        ),
    )


@when("the deployed inventory is checked against this specification")
def _the_inventory_is_checked(deployment: dict[str, Any], repo_root: Path) -> None:
    deployment["non_conformance"] = _non_conformance(repo_root, deployment["inventory"])


@then("the deployment SHALL be rejected as non-conforming")
def _the_deployment_is_rejected(deployment: dict[str, Any]) -> None:
    found = deployment["non_conformance"]

    assert found, "a deployment hosting the agent server was accepted"
    assert any(deployed.AGENT_SERVER in line for line in found)
    assert any("specification change" in line for line in found)


# -- the agent server listens on nothing ------------------------------------


@given("the agent server is running on a developer machine")
def _the_agent_server_is_running(deployment: dict[str, Any], tmp_path: Path) -> None:
    deployment["root"] = _a_developer_machine(tmp_path)
    deployment["environment"] = _denying(tmp_path, "unlistenable", DENY_LISTENING)


@when("its open network ports are inspected")
def _its_open_network_ports_are_inspected(deployment: dict[str, Any]) -> None:
    """Denied rather than counted: the process may not open one, and still answers."""
    deployment["answers"] = _agent_answers(
        deployment["root"],
        {"where_is": {"asset_id": CRATE}, "list_assets": {}},
        deployment["environment"],
    )
    deployment["listener"] = subprocess.run(
        [sys.executable, "-c", "import socket; socket.create_server(('127.0.0.1', 0))"],
        cwd=deployment["root"],
        capture_output=True,
        text=True,
        check=False,
        env=deployment["environment"],
    )


@then("it SHALL be listening on none")
def _it_is_listening_on_none(deployment: dict[str, Any]) -> None:
    assert CRATE in deployment["answers"]["where_is"]
    assert CRATE in deployment["answers"]["list_assets"]
    assert deployment["listener"].returncode != 0, "the prohibition was not in force"
    assert "may not listen" in deployment["listener"].stderr


# -- both local tools work with nothing hosted reachable ---------------------


@given("every hosted component is unreachable")
def _every_hosted_component_is_unreachable(deployment: dict[str, Any], tmp_path: Path) -> None:
    deployment["root"] = _a_developer_machine(tmp_path)
    deployment["environment"] = _denying(tmp_path, "offline", DENY_NETWORK)


@when("a developer validates an export and asks the agent server where an asset lives")
def _a_developer_validates_and_asks(deployment: dict[str, Any]) -> None:
    deployment["validated"] = _canon(
        deployment["root"], "validate", CRATE_EXPORT, env=deployment["environment"]
    )
    deployment["answers"] = _agent_answers(
        deployment["root"], {"where_is": {"asset_id": CRATE}}, deployment["environment"]
    )


@then("both SHALL complete normally")
def _both_complete_normally(deployment: dict[str, Any]) -> None:
    validated = deployment["validated"]

    assert validated.returncode == CLEAN, validated.stdout + validated.stderr
    assert "PASSING" in validated.stdout
    assert "props/crate" in deployment["answers"]["where_is"]
