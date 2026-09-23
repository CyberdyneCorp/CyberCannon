"""The end-to-end stack: its configuration is complete, and its failures are legible.

Two regressions, one cause. CI's e2e job reported *116 errors, 6 passed*, every
error identical — ``docker compose ... up --detach --wait --remove-orphans``
returned 1 — and not one of them said why, because the fixture ran compose
through `subprocess` with `capture_output=True` and let only the
`CalledProcessError` escape. A stack failure that produces no diagnosis is the
expensive half: the cause then has to be found by reading the repository instead
of by reading the log.

So this suite fixes both halves in the place each of them lives:

* **the stack's configuration is checked against the code that reads it.**
  `deploy/e2e/compose.yaml` was missing `CANON_WRITE_BACK_TIMEOUT_S` and
  `CANON_DRAIN_WINDOW_S`, which are required settings, so the api refused to
  boot naming them, its health check never passed, and `up --wait` failed before
  a single assertion ran. The compose file is read here against
  `cybercanon.adapters.wiring.configuration`'s own table, so the two cannot
  drift apart again — the same trick `deploy/coolify.yaml` is already held to;
* **a refusal carries docker's own words.** Verified against a stub `docker` on
  `PATH` that fails the way compose fails, because the assertion that matters is
  *"the message names the real cause"* and that is a property of the fixture,
  not of the engine. It therefore runs on a machine with no docker — which is
  exactly the machine this was diagnosed on.

This file is `tooling` rather than `e2e` on purpose: it verifies the build, it
needs nothing running, and a check that only runs in the job that is already
broken is a check nobody gets to use.
"""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import pytest
from ruamel.yaml import YAML

from cybercanon.adapters.wiring.configuration import (
    AUTH_AUDIENCE,
    AUTH_ISSUER,
    AUTH_KEY_SET_URL,
    DRAIN_WINDOW,
    WRITE_BACK_TIMEOUT,
    load,
    missing_from,
)

pytestmark = pytest.mark.tooling

COMPOSE = Path("deploy/e2e/compose.yaml")
SERVE = Path("deploy/e2e/serve-repository.sh")
API_IMAGE = Path("deploy/e2e/api.Dockerfile")
FIXTURE = Path("tests/e2e/stack.py")

REFUSED = "dependency failed to start: container cybercanon-e2e-api-1 is unhealthy"
"""What docker says. Previously swallowed; it is the first line of the answer."""

LOGGED = (
    "the service cannot start: 2 required environment variable(s) are not set "
    f"— {WRITE_BACK_TIMEOUT}, {DRAIN_WINDOW}."
)
"""What the container says. It is the *real* cause, and it is only in the log."""

NDJSON = (
    '{"Service":"api","State":"exited","Health":"","ExitCode":1}\n'
    '{"Service":"web","State":"running","Health":"healthy"}'
)
JSON_ARRAY = (
    '[{"Service":"api","State":"exited","Health":"","ExitCode":1},'
    '{"Service":"web","State":"running","Health":"healthy"}]'
)
"""Both shapes `docker compose ps --format json` has shipped as."""

SERVICES = ("postgres", "minio", "repository", "issuer", "api", "web")
"""What `docker compose config --services` answers for this stack."""


# --------------------------------------------------------------------------
# The stack's own configuration
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_environment(repo_root: Path) -> dict[str, str]:
    """What `deploy/e2e/compose.yaml` gives the api service."""
    document = YAML(typ="safe").load((repo_root / COMPOSE).read_text(encoding="utf-8"))
    return {name: str(value) for name, value in document["services"]["api"]["environment"].items()}


def test_the_stack_gives_the_api_every_variable_it_refuses_to_start_without(
    api_environment: dict[str, str],
) -> None:
    """The regression: two required settings were absent and the boot was refused."""
    absent = missing_from(api_environment)

    assert not absent, (
        f"{COMPOSE} does not set {', '.join(absent)}, so the api refuses to start "
        "naming them, its health check never passes, and `up --wait` fails before "
        "any assertion runs"
    )


def test_the_stack_configuration_is_one_the_service_can_read(
    api_environment: dict[str, str],
) -> None:
    """Complete is not enough: it has to load, D7's ordered pair included."""
    configuration = load(api_environment)

    assert configuration.rollover.drains_longer_than_write_back


def test_the_repository_service_provides_the_daemon_it_runs(repo_root: Path) -> None:
    """`git daemon` is Alpine's `git-daemon` package, which `alpine/git` lacks.

    Without it the entry point exits with *"git: 'daemon' is not a git
    command"*, and every other service waits on a repository that never
    answers.
    """
    script = (repo_root / SERVE).read_text(encoding="utf-8")

    assert "git daemon" in script, "this script is what serves the source of truth"
    assert "git-daemon" in script, (
        f"{SERVE} runs `git daemon`, which `alpine/git` does not install: "
        "Alpine ships it as the separate `git-daemon` package"
    )


def test_the_api_image_passes_no_argument_its_entry_point_ignores(repo_root: Path) -> None:
    """`cybercanon.api.__main__` parses nothing, so a flag here configures nothing."""
    started = (repo_root / API_IMAGE).read_text(encoding="utf-8")
    command = started[started.index("CMD") :]

    assert "--host" not in command
    assert "--port" not in command


# --------------------------------------------------------------------------
# The identity service: an address something actually serves
# --------------------------------------------------------------------------

WEB_SIGN_IN = (
    "PUBLIC_CANON_AUTH_ISSUER",
    "PUBLIC_CANON_AUTH_CLIENT_ID",
    "PUBLIC_CANON_AUTH_AUDIENCE",
)
"""What `apps/cybercanon/web/src/lib/config.ts` reads to offer sign-in at all."""


@pytest.fixture(scope="module")
def stack_document(repo_root: Path) -> dict:
    return YAML(typ="safe").load((repo_root / COMPOSE).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def web_environment(stack_document: dict) -> dict[str, str]:
    """What `deploy/e2e/compose.yaml` gives the web service."""
    declared = stack_document["services"]["web"]["environment"]
    return {name: str(value) for name, value in declared.items()}


def test_the_key_set_address_names_a_service_this_stack_runs(
    api_environment: dict[str, str], stack_document: dict
) -> None:
    """The regression: it named `http://api:8000/e2e-issuer/jwks.json`, which 400s.

    Nothing served that address — the api's catch-all refuses any path carrying
    no surface version — so no credential could ever verify, the browser suites
    could only assert the signed-out half of the application, and every
    verification that needed a session was silently out of reach.
    """
    host = urlsplit(api_environment[AUTH_KEY_SET_URL]).hostname

    assert host in stack_document["services"], (
        f"{COMPOSE} retrieves the key set from {host!r}, which is not a service "
        "in this stack, so no credential can verify and no signed-in screen can "
        "be reached"
    )
    assert host != "api", "the api serves no key set: it is the thing verifying against one"


def test_the_issuer_mints_for_the_audience_the_api_trusts(
    api_environment: dict[str, str], stack_document: dict
) -> None:
    """Issuer and audience are checked by name, so a mismatch is a silent refusal."""
    issuer = stack_document["services"]["issuer"]["environment"]

    assert issuer["ISSUER_AUDIENCE"] == api_environment[AUTH_AUDIENCE]
    assert issuer["ISSUER_URL"].rstrip("/") == api_environment[AUTH_ISSUER].rstrip("/")


def test_the_issued_credential_is_entitled_to_the_project_the_api_serves(
    api_environment: dict[str, str], stack_document: dict
) -> None:
    """Entitlement is a claim, so a token for another project reads nothing here."""
    issuer = stack_document["services"]["issuer"]["environment"]
    entitled = [name.strip() for name in str(issuer["ISSUER_PROJECTS"]).split(",")]

    assert api_environment["CANON_PROJECT"] in entitled


def test_the_issued_groups_are_ones_the_api_maps_to_a_role(
    api_environment: dict[str, str], stack_document: dict
) -> None:
    """An unmapped group grants nothing, which reads as a session that can do nothing."""
    issuer = stack_document["services"]["issuer"]["environment"]
    held = {name.strip() for name in str(issuer["ISSUER_GROUPS"]).split(",") if name.strip()}
    mapped = {
        pair.split("=", 1)[0].strip()
        for pair in api_environment["CANON_AUTH_GROUP_ROLES"].split(",")
        if "=" in pair
    }

    assert held and held <= mapped, f"{held - mapped} map to no role, so they grant nothing"


@pytest.mark.parametrize("name", WEB_SIGN_IN)
def test_the_application_is_told_how_to_sign_somebody_in(
    web_environment: dict[str, str], name: str
) -> None:
    """Without these the application states sign-in is unavailable and renders on.

    That is the right behaviour for a misconfigured deployment and the wrong
    state for an end-to-end stack to be permanently stuck in: it is why no
    signed-in screen was ever exercised.
    """
    assert web_environment.get(name, "").strip(), (
        f"{COMPOSE} does not give the web application {name}, so sign-in is "
        "unavailable and only the signed-out half of the application can be tested"
    )


def test_the_application_signs_in_against_the_same_issuer_the_api_trusts(
    web_environment: dict[str, str], api_environment: dict[str, str]
) -> None:
    """One issuer and one audience, or the credential is minted for nobody here."""
    assert web_environment["PUBLIC_CANON_AUTH_ISSUER"].rstrip("/") == (
        api_environment[AUTH_ISSUER].rstrip("/")
    )
    assert web_environment["PUBLIC_CANON_AUTH_AUDIENCE"] == api_environment[AUTH_AUDIENCE]


# --------------------------------------------------------------------------
# The fixture: a failure that says why
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture(repo_root: Path) -> ModuleType:
    """`tests/e2e/stack.py`, loaded by path — it is not an importable package."""
    specification = importlib.util.spec_from_file_location("e2e_stack", repo_root / FIXTURE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _stub_docker(directory: Path, *, listing: str = NDJSON) -> None:
    """A `docker` that fails the way compose fails, and answers `ps` and `logs`."""
    script = directory / "docker"
    script.write_text(
        "#!/bin/sh\n"
        'arguments=" $* "\n'
        'case "$arguments" in\n'
        '  *" up "*)\n'
        '    echo "cybercanon-e2e-api-1  Creating"\n'
        f'    echo "{REFUSED}" >&2\n'
        "    exit 1;;\n"
        '  *" ps --all --format json "*)\n'
        f"    cat <<'LISTING'\n{listing}\nLISTING\n"
        "    exit 0;;\n"
        '  *" ps --all "*)\n'
        '    echo "NAME                     STATUS"\n'
        '    echo "cybercanon-e2e-api-1     Exited (1)"\n'
        "    exit 0;;\n"
        '  *" config --services "*)\n'
        f"    printf '%s\\n' {' '.join(SERVICES)}\n"
        "    exit 0;;\n"
        '  *" logs "*)\n'
        f'    echo "api-1 | {LOGGED}"\n'
        "    exit 0;;\n"
        "  *) exit 0;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def stubbed(fixture: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    _stub_docker(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    return fixture


def _enter(stubbed: ModuleType, repo_root: Path) -> None:
    with stubbed.compose_stack(repo_root):
        pytest.fail("the stack cannot have come up")


def _failure(stubbed: ModuleType, repo_root: Path) -> str:
    with pytest.raises(stubbed.StackDidNotStart) as raised:
        _enter(stubbed, repo_root)
    return str(raised.value)


def test_the_stack_rebuilds_its_images_before_it_starts_them(
    fixture: ModuleType, repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`compose up` builds only a *missing* image, which is how a suite goes stale.

    Without `--build`, a machine that has run this suite before starts the API
    and the web application it built the last time somebody rebuilt them by
    hand. Every assertion then passes about code that is not running, and the
    run reports green — the same failure as a silent skip, wearing a passing
    result. This is the regression test for that.
    """
    recorded = tmp_path / "invocations"
    script = tmp_path / "docker"
    script.write_text(
        "#!/bin/sh\n"
        f'echo " $* " >> "{recorded}"\n'
        'case " $* " in\n'
        '  *" up "*) exit 1;;\n'
        "  *) exit 0;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(fixture.StackDidNotStart), fixture.compose_stack(repo_root):
        pytest.fail("the stack cannot have come up")

    ups = [line for line in recorded.read_text(encoding="utf-8").splitlines() if " up " in line]
    assert ups, "the stack never ran `compose up`"
    assert all("--build" in line for line in ups), ups


def test_a_refused_stack_reports_what_docker_printed(stubbed: ModuleType, repo_root: Path) -> None:
    """The stderr that used to reach only a `CalledProcessError` nobody printed."""
    assert REFUSED in _failure(stubbed, repo_root)


def test_a_refused_stack_reports_the_log_of_the_container_that_failed(
    stubbed: ModuleType, repo_root: Path
) -> None:
    """The real cause: docker's exit code names a container, the container names the bug."""
    reported = _failure(stubbed, repo_root)

    assert "docker compose logs api" in reported
    assert LOGGED in reported


def test_a_refused_stack_reports_what_the_containers_are(
    stubbed: ModuleType, repo_root: Path
) -> None:
    assert "docker compose ps" in _failure(stubbed, repo_root)


def test_only_the_services_that_are_not_healthy_are_read(
    stubbed: ModuleType, repo_root: Path
) -> None:
    """A healthy service's log is noise in the message that has to be read."""
    assert stubbed.unhealthy(repo_root) == ("api",)


@pytest.mark.parametrize("listing", [NDJSON, JSON_ARRAY], ids=["ndjson", "array"])
def test_both_listing_shapes_docker_has_published_are_read(
    fixture: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    listing: str,
) -> None:
    _stub_docker(tmp_path, listing=listing)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert fixture.unhealthy(repo_root) == ("api",)


def test_a_listing_that_cannot_be_read_yields_every_service(
    fixture: ModuleType, repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Too many logs is a nuisance; no logs is the failure this suite exists for."""
    _stub_docker(tmp_path, listing="not json at all")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert fixture.unhealthy(repo_root) == SERVICES
