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

import pytest
from ruamel.yaml import YAML

from cybercanon.adapters.wiring.configuration import (
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

SERVICES = ("postgres", "minio", "repository", "api", "web")
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
