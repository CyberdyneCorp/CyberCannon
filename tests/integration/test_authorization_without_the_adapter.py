"""Tasks 8.4 and 8.7 — the core decides, and validates, with no identity anywhere.

Two claims this change makes that are only worth anything if they are checked
from outside the process that makes them:

* *"authorization behaviour can be exercised with no identity service present"*
  — so a fresh interpreter evaluates the whole operation matrix over constructed
  actors and is then asked which modules it had to load. If the verification
  adapter, `joserfc`, `keyring` or `httpx` are among them, the token format has
  reached the core and the requirement is broken however green the rest is.
* *"validation SHALL complete normally"* on a machine that has never signed in —
  so a second interpreter runs `canon validate` over a real export with every
  outbound network call made to fail and no credential stored anywhere.

Both run as subprocesses, because both are assertions about *what was not
imported* and *what was not reached*, and by the time this suite is running the
test process has imported all of it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from game_repo import MECH_EXPORT, GameRepo, build_game_repo

pytestmark = pytest.mark.integration

FORBIDDEN = ("cybercanon.adapters.outbound.auth", "joserfc", "keyring", "httpx")
"""Modules an authorization decision must not have needed."""

DECIDES = """
import sys

from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.policy import Operation, Subject, decide
from cybercanon.domain.tenancy import ProjectRef, Tenant

director = Actor(
    id=ActorId("auth|ana"),
    display_name="Ana",
    roles=(Role.ART_DIRECTOR,),
    projects=("Ronin",),
    tenant=Tenant("cyberdyne"),
)
elsewhere = Subject(project=ProjectRef("Ronin", tenant=Tenant("ironwood-studios")))

here = Subject(project="Ronin")
decisions = {operation: decide(director, operation, here) for operation in Operation}
assert len(decisions) == len(list(Operation))
assert decide(director, Operation.READ_PROJECT, elsewhere).refused

loaded = [name for name in sys.modules if name.startswith(%r)]
print("|".join(sorted(loaded)))
"""


def _run(source: str, *, root: Path | None = None, environment: dict[str, str] | None = None):
    """A fresh interpreter, with this repository importable and nothing else assumed."""
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=root,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_every_authorization_decision_is_made_with_the_adapter_never_imported() -> None:
    forbidden = tuple(FORBIDDEN)
    completed = _run(DECIDES % (forbidden,))

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "", (
        "an authorization decision loaded "
        f"{completed.stdout.strip()}. The credential's representation has reached "
        "the core, and the policy can no longer be exercised without an identity "
        "service (auth-integration)."
    )


def test_the_guard_is_over_something_that_could_fail() -> None:
    """A guard over nothing passes for the wrong reason.

    The same script, with the verification adapter imported first. If this does
    not report the modules, the check above is asserting an empty set.
    """
    poisoned = "import cybercanon.adapters.outbound.auth.cyberdyne\n" + DECIDES % (FORBIDDEN,)

    completed = _run(poisoned)

    assert completed.returncode == 0, completed.stderr
    assert "joserfc" in completed.stdout
    assert "cybercanon.adapters.outbound.auth" in completed.stdout


VALIDATES = """
import socket
import sys


def refuse(*arguments, **keywords):
    raise OSError("this machine has no network")


socket.socket = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse

from cybercanon.cli.main import main

try:
    main(["validate", %r])
except SystemExit as exit:
    print(f"exit={exit.code}")
"""


@pytest.fixture(scope="module")
def game(tmp_path_factory: pytest.TempPathFactory) -> GameRepo:
    """A real working copy with specifications and a conforming export in it."""
    return build_game_repo(tmp_path_factory.mktemp("never-signed-in"))


def test_validation_completes_on_a_machine_that_has_never_signed_in(
    game: GameRepo, tmp_path: Path
) -> None:
    """No credential stored anywhere, and every network call configured to fail.

    `HOME` points at an empty directory the test just made, so there is nothing
    for a credential store to find even if something asked one — and the socket
    module is replaced before `canon` is imported, so a network call at import
    time would fail as loudly as one during the run.
    """
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path / "a-machine-that-never-signed-in"),
        "PYTHONPATH": ":".join(sys.path),
    }
    completed = _run(VALIDATES % (MECH_EXPORT,), root=game.root, environment=environment)

    assert "exit=0" in completed.stdout, f"{completed.stdout}\n{completed.stderr}"
    assert "PASSING" in completed.stdout, "the run has to have happened, not merely exited 0"
