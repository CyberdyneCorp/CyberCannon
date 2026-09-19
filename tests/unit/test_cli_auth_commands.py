"""Task 8.6 — `canon auth` as a person actually runs it.

The use cases are covered in `test_use_case_sign_in.py`; what is covered here is
the inbound adapter over them, because the two things this surface must not do
are both things only the surface can do:

* **print a credential.** The prose and the `--json` document both say *where*
  the credential is and never *what* it is, so neither a terminal scrollback nor
  a script capturing standard output ends up holding a token.
* **fail unhelpfully when nothing is configured.** `canon` is local-first and
  most machines running it have never heard of an identity service, so an
  unconfigured sign-in is a refusal naming the two variables rather than a
  traceback.

The device grant goes to standard error even in `--json` mode: it is an
instruction the person has to act on *before* there is a result, and the
structured document on standard output is the result.
"""

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from cybercanon.adapters.inbound.cli.app import build_app
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.interactive_sign_in import (
    USER_CODE,
    VERIFICATION_URI,
    InMemoryInteractiveSignIn,
)

ISSUED = Credential("the-credential-the-issuer-signed")

COULD_NOT_RUN = 2


@pytest.fixture
def container() -> Container:
    """A container wired for signing in, over the in-memory fakes."""
    fakes = build_fakes()
    return Container(
        spec_store=fakes["spec_store"],
        mesh_inspector=fakes["mesh_inspector"],
        credential_store=fakes["credential_store"],
        interactive_sign_in=InMemoryInteractiveSignIn(issues=ISSUED),
    )


@pytest.fixture
def app(container: Container) -> typer.Typer:
    return build_app(container)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_signing_in_stores_the_credential_and_says_where(
    app: typer.Typer, container: Container, runner: CliRunner
) -> None:
    result = runner.invoke(app, ["auth", "login"])

    assert result.exit_code == 0
    assert container.credential_store.load() == ISSUED
    assert VERIFICATION_URI in result.output
    assert USER_CODE in result.output


def test_nothing_the_command_writes_contains_the_credential(
    app: typer.Typer, runner: CliRunner
) -> None:
    """A terminal scrollback is shared far more often than anybody intends."""
    written = runner.invoke(app, ["auth", "login"]).output
    written += runner.invoke(app, ["auth", "status", "--json"]).output

    assert ISSUED.value not in written


def test_status_reports_whether_and_the_document_says_the_same(
    app: typer.Typer, runner: CliRunner
) -> None:
    before = runner.invoke(app, ["auth", "status", "--json"])
    runner.invoke(app, ["auth", "login"])
    after = runner.invoke(app, ["auth", "status", "--json"])

    assert json.loads(before.stdout)["signed_in"] is False
    assert json.loads(after.stdout)["signed_in"] is True


def test_signing_out_removes_it_and_twice_is_not_an_error(
    app: typer.Typer, container: Container, runner: CliRunner
) -> None:
    runner.invoke(app, ["auth", "login"])

    first = runner.invoke(app, ["auth", "logout"])
    second = runner.invoke(app, ["auth", "logout"])

    assert (first.exit_code, second.exit_code) == (0, 0)
    assert container.credential_store.load() is None
    assert json.loads(runner.invoke(app, ["auth", "logout", "--json"]).stdout)["removed"] is False


def test_an_unconfigured_machine_is_told_what_to_configure(runner: CliRunner) -> None:
    """Local-first: no identity service is the ordinary case, not a crash."""
    fakes = build_fakes()
    bare = Container(spec_store=fakes["spec_store"], mesh_inspector=fakes["mesh_inspector"])

    result = runner.invoke(build_app(bare), ["auth", "login"])

    assert result.exit_code == COULD_NOT_RUN
    assert "CANON_AUTH_ISSUER" in result.output
    assert "CANON_AUTH_CLIENT_ID" in result.output


def test_the_device_grant_is_a_diagnostic_and_the_document_is_the_result(
    app: typer.Typer, runner: CliRunner
) -> None:
    """In `--json` mode standard output carries the document and nothing else."""
    result = runner.invoke(app, ["auth", "login", "--json"])

    assert json.loads(result.stdout)["command"] == "auth login"
    assert USER_CODE not in result.stdout
