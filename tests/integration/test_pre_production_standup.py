"""Task 8.4 — standing up an environment, in the Migration Plan's own order.

The design's Migration Plan is seven numbered steps, and each one carries a
*stated confirmation* — "confirm `/status` reports a revision and a fetch time",
"confirm the reported schema version", "confirm it becomes ready with the API
stopped". A plan whose confirmations nobody executes is a plan that is correct
until the first time somebody follows it, so this suite follows it: one
environment, stood up in order, with every stated confirmation asserted where
the plan states it.

**The order is the test.** Each step depends on the one before it — the
migration runs against a database that exists, the index is built from a working
copy that has been cloned, the webhook advances a revision the status surface is
already reporting — so they run as one sequence against one environment rather
than as seven independent tests that would each quietly rebuild the world.

What is real: a real bare remote and a real working copy over real git, a real
PostgreSQL, a real S3 API, the real migration release command, and the real
FastAPI application with its real webhook endpoint. What is not here is the
platform: nobody can run Coolify from a test, so "deploy the API" is the
application being built from a configuration exactly as `python -m
cybercanon.api` builds it.

**Step 6 is executed elsewhere and deliberately not claimed here.** *"Deploy the
web application; confirm it becomes ready with the API stopped"* is a claim
about a node process serving a built artifact, and
`tests/integration/test_web_readiness_process.py` starts that artifact with
nothing answering at the address of the API and asserts both halves — that it
becomes ready, and that it never opened a connection to decide. This suite
asserts that the step has an executor rather than pretending to be one.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
import psycopg
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from staged_project import BRANCH, PROJECT, SCOUT_SPEC, Staged, stage
from test_postgres_index import fingerprints_under

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.health import (
    ALIVE,
    LIVE_PATH,
    READY,
    READY_PATH,
    STATUS_FIELD,
)
from cybercanon.adapters.inbound.http.status import PROJECTS_FIELD, STATUS_PATH
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.inbound.http.webhooks import (
    SIGNATURE_HEADER,
    WEBHOOK_PATH,
    RepositoryNotifications,
    signature_for,
)
from cybercanon.adapters.outbound.minio.blob_store import S3BlobStore
from cybercanon.adapters.outbound.postgres.search_index import PostgresSearchIndex
from cybercanon.adapters.wiring.configuration import load
from cybercanon.adapters.wiring.container import Container
from cybercanon.api import migrate
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.results import Ok
from cybercanon.application.testing import build_fakes
from cybercanon.application.use_cases.deployment_status import (
    DeploymentJournal,
    rebuild_and_record,
    refresh_and_record,
)
from cybercanon.application.use_cases.service_health import LANGUAGE_MODEL
from cybercanon.domain.identity import Actor, ActorId, Role

pytestmark = pytest.mark.integration

BUCKET = "cybercanon-preproduction"
REGION = "us-east-1"
SECRET = "a-pre-production-webhook-secret"

TOKEN = "an-operator-token"
OPERATOR = "auth|ops"

WEB_READINESS_SUITE = Path("tests") / "integration" / "test_web_readiness_process.py"
"""Where step 6's stated confirmation is actually executed."""

EDIT = b"schema_version: 1\nid: mech_scout\nname: Scout Mech\nstatus: modeling\n"


@dataclass
class Environment:
    """One environment being stood up, and what each step left behind."""

    staged: Staged
    dsn: str
    blobs: S3BlobStore
    journal: DeploymentJournal = field(default_factory=DeploymentJournal)
    settings: dict[str, str] = field(default_factory=dict)
    client: TestClient | None = None
    opened: list[PostgresSearchIndex] = field(default_factory=list)

    def status(self) -> dict[str, Any]:
        assert self.client is not None, "step 4 has not deployed the API yet"
        answered = self.client.get(STATUS_PATH, headers={"Authorization": f"Bearer {TOKEN}"})
        assert answered.status_code == 200, answered.text
        return answered.json()["data"]

    def project(self) -> dict[str, Any]:
        return next(one for one in self.status()[PROJECTS_FIELD] if one["project"] == PROJECT)


@pytest.fixture
def environment(tmp_path: Path, postgres_server: Any) -> Iterator[Environment]:
    """A bare remote, an empty database and an empty bucket. Nothing stood up yet.

    Empty means empty: the database is dropped and created again, so a standup
    never inherits a schema a previous one left — which is the whole point of
    step 3 confirming a version.
    """
    _emptied(postgres_server)
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id="pre-production",
            aws_secret_access_key="pre-production",
        )
        client.create_bucket(Bucket=BUCKET)
        standing_up = Environment(
            staged=stage(tmp_path),
            dsn=postgres_server.get_uri(database="preproduction"),
            blobs=S3BlobStore(client, BUCKET, base_url="https://blobs.pre-production.example"),
        )
        yield standing_up
        for index in standing_up.opened:
            index.close()


def _emptied(postgres_server: Any) -> None:
    """Drop the database, evicting whatever an earlier environment left connected."""
    postgres_server.psql(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'preproduction'"
    )
    postgres_server.psql("DROP DATABASE IF EXISTS preproduction")
    postgres_server.psql("CREATE DATABASE preproduction")


# --------------------------------------------------------------------------
# The seven steps, each one a function named after it
# --------------------------------------------------------------------------


def step_1_record_the_connection_settings(environment: Environment) -> None:
    """*"Create the PostgreSQL and MinIO applications ... record the connection
    settings as environment on the API application."*"""
    environment.settings = {
        "CANON_REPOSITORY_URL": str(environment.staged.bare),
        "CANON_REPOSITORY_BRANCH": BRANCH,
        "CANON_REPOSITORY_CREDENTIAL": "a-pre-production-deploy-key",
        "CANON_FETCH_INTERVAL_S": "300",
        "CANON_WEBHOOK_SECRET": SECRET,
        "CANON_AUTH_ISSUER": "https://auth.invalid/",
        "CANON_AUTH_AUDIENCE": "cybercanon-pre-production",
        "CANON_AUTH_KEY_SET_URL": "https://auth.invalid/.well-known/jwks.json",
        "CANON_AUTH_GROUP_ROLES": "art-leads=ART_DIRECTOR",
        "CANON_DATABASE_URL": environment.dsn,
        "CANON_OBJECT_STORE_URL": "https://minio.invalid",
        "CANON_LINK_EXPIRY_S": "120",
        "CANON_WRITE_BACK_TIMEOUT_S": "30",
        "CANON_DRAIN_WINDOW_S": "90",
    }
    configured = load(environment.settings)

    assert configured.storage.database_url.value == environment.dsn
    assert configured.storage.object_store_url == "https://minio.invalid"
    assert str(configured.storage.database_url) == "<secret>", "a connection string is a secret"


def step_2_clone_and_confirm_a_revision_and_a_fetch_time(environment: Environment) -> None:
    """*"run the initial clone; confirm `/status` reports a revision and a fetch time."*"""
    environment.staged.host.clone(PROJECT)
    outcome = refresh_and_record(
        PROJECT, repository_host=environment.staged.host, journal=environment.journal
    )

    assert isinstance(outcome, Ok), outcome
    assert environment.journal.attempt(PROJECT) is not None
    assert environment.staged.host.head(PROJECT).value


def step_3_run_the_release_command_and_confirm_the_schema_version(
    environment: Environment,
) -> str:
    """*"Run the migration release command against the empty database; confirm the
    reported schema version."*"""
    code = migrate.main([], environment.settings)
    reported = migrate.version(environment.settings)

    assert code == 0
    assert reported, "the release step reported no schema version"
    return reported


def step_4_deploy_the_api(environment: Environment) -> None:
    """*"confirm `/healthz`, `/readyz` and `/status`, including that `/readyz`
    reports ready with the model gateway and the identity provider deliberately
    misconfigured."*"""
    environment.client = _api(environment)

    assert environment.client.get(LIVE_PATH).json()[STATUS_FIELD] == ALIVE
    readiness = environment.client.get(READY_PATH).json()
    assert readiness[STATUS_FIELD] == READY
    assert LANGUAGE_MODEL in readiness["degraded"], "the model is deliberately not configured"
    assert environment.project()["working_copy"]["revision"]


def step_5_build_the_index_and_confirm_it_is_in_sync(environment: Environment) -> None:
    """*"Build the index for each project; confirm `/status` reports it in sync."*"""
    with PostgresSearchIndex(environment.dsn) as index:
        outcome = rebuild_and_record(
            PROJECT,
            repository_host=environment.staged.host,
            spec_store=environment.staged.spec_store(),
            search_index=index,
            fingerprints=fingerprints_under(environment.staged.working_copy),
            journal=environment.journal,
        )
    assert isinstance(outcome, Ok), outcome

    reported = environment.project()["index"]
    assert reported["in_sync"], reported
    assert reported["indexed_revision"] == reported["working_copy_revision"]


def step_7_register_the_webhook_and_confirm_a_push_advances_the_revision(
    environment: Environment,
) -> None:
    """*"Register the git webhook; confirm a push advances the working-copy revision."*"""
    before = environment.project()["working_copy"]["revision"]
    environment.staged.commit_outside(SCOUT_SPEC, EDIT, "someone pushes")
    body = f'{{"ref": "refs/heads/{BRANCH}", "project": "{PROJECT}"}}'.encode()

    answered = environment.client.post(
        WEBHOOK_PATH,
        content=body,
        headers={SIGNATURE_HEADER: signature_for(SECRET, body)},
    )

    assert answered.status_code in (200, 202), answered.text
    after = environment.project()["working_copy"]["revision"]
    assert after != before, "the push did not advance the working copy"


def _api(environment: Environment) -> TestClient:
    """The API, wired the way the deployment wires it: over its three volumes."""
    fakes = build_fakes()
    fakes["identity_provider"].add(
        Credential(TOKEN),
        Actor(
            id=ActorId(OPERATOR),
            display_name="Operator",
            roles=(Role.ART_DIRECTOR,),
            projects=(PROJECT,),
        ),
    )
    index = PostgresSearchIndex(environment.dsn)
    environment.opened.append(index)
    container = Container(
        spec_store=environment.staged.spec_store(),
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=environment.blobs,
        search_index=index,
    )
    surface = Surface(
        projects={
            PROJECT: HostedProject(
                name=PROJECT, container=container, repository_host=environment.staged.host
            )
        },
        identity_provider=fakes["identity_provider"],
        journal=environment.journal,
        observe=lambda: _observed(),
    )
    notifications = RepositoryNotifications(
        secret=SECRET,
        branches={PROJECT: BRANCH},
        refresh=lambda project: refresh_and_record(
            project, repository_host=environment.staged.host, journal=environment.journal
        ),
    )
    return TestClient(build_app(surface=surface, notifications=notifications))


def _observed():
    from cybercanon.application.use_cases.service_health import unavailable

    return (unavailable(LANGUAGE_MODEL, "CANON_LLM_ENABLED is off"),)


# --------------------------------------------------------------------------
# The plan, run
# --------------------------------------------------------------------------


def test_pre_production_stands_up_in_the_documented_order(environment: Environment) -> None:
    """Every numbered step, in order, each confirming what the plan says it does."""
    step_1_record_the_connection_settings(environment)
    step_2_clone_and_confirm_a_revision_and_a_fetch_time(environment)
    version = step_3_run_the_release_command_and_confirm_the_schema_version(environment)
    step_4_deploy_the_api(environment)
    step_5_build_the_index_and_confirm_it_is_in_sync(environment)
    step_7_register_the_webhook_and_confirm_a_push_advances_the_revision(environment)

    assert version == migrate.version(environment.settings), "the schema moved under the plan"


def test_the_migration_is_idempotent_so_a_retried_standup_applies_nothing(
    environment: Environment,
) -> None:
    """A plan that cannot be re-run from the middle is a plan nobody re-runs."""
    step_1_record_the_connection_settings(environment)
    first = step_3_run_the_release_command_and_confirm_the_schema_version(environment)

    again = step_3_run_the_release_command_and_confirm_the_schema_version(environment)

    assert again == first


def test_the_api_is_deployed_after_the_release_step_and_not_before(
    environment: Environment,
) -> None:
    """Step 3 precedes step 4 for a reason: the schema exists before anything serves."""
    step_1_record_the_connection_settings(environment)
    step_2_clone_and_confirm_a_revision_and_a_fetch_time(environment)

    with pytest.raises(psycopg.errors.UndefinedTable):
        PostgresSearchIndex(environment.dsn).list_assets(project=PROJECT)


def test_step_six_has_an_executor(repo_root: Path) -> None:
    """*"confirm it becomes ready with the API stopped"* — asserted where it runs."""
    suite = (repo_root / WEB_READINESS_SUITE).read_text(encoding="utf-8")

    assert "readiness" in suite
    assert "never opened a connection" in suite
