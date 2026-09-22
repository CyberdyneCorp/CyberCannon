"""Task 3.5 — rollback is a redeploy of a recorded digest, and never a rebuild.

`deploy/README.md` says so and `tools/canon_release` implements the ledger, but
the claim the specification makes is about *artifacts*: deploy revision N, then
N-1, and what serves is the image that was already built and already verified.
A document and a ledger can both be right about a procedure nobody has run.

So this runs it, end to end, with real images:

1. build the API image from the two most recent revisions that changed what
   goes into it, extracted with `git archive` so each build sees exactly what
   that revision contained, and record each digest in a ledger of its own. The
   revisions are chosen that way rather than as `HEAD` and `HEAD~1` because the
   image is content-addressed: a commit that only edited a specification builds
   to the same digest, correctly, and a drill between two identical artifacts
   would deploy one image twice and pass;
2. deploy N: run the container **by digest**, and ask it `/healthz`;
3. the build contexts are deleted as soon as each image exists. There is
   nothing on this machine a rebuild could be performed from by the time the
   rollback runs, which is what makes *"with no rebuild"* a fact rather than an
   intention;
4. ask `canon_release rollback` for the digest of N-1, run **that** digest, and
   assert it serves and that what is running is the earlier artifact.

The images are built with the flags `deploy/README.md` documents for the
pipeline (`--provenance=false --sbom=false`), because a digest recorded from a
differently-built image is a digest no rollback could match — see
`tests/tooling/test_container_artifacts.py`.

Skipped with no container engine, or in a checkout with no previous revision to
roll back to, saying which. A test that reported green having deployed nothing
would be worse than one that says it did not run.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ENGINE = "docker"
IMAGE = "api"
DOCKERFILE = Path("deploy") / "api.Dockerfile"

REPRODUCIBLE: tuple[str, ...] = ("--provenance=false", "--sbom=false")
"""The pipeline's flags. A digest recorded from another build is not this one."""

NO_ENGINE = (
    "no container engine on this machine: rolling back is redeploying a built "
    "artifact, and there is nothing here to build one with"
)
NO_PREVIOUS = (
    "this checkout has no two revisions that change what goes into the image, so "
    "there is no N-1 whose artifact differs from N's"
)

IMAGE_CONTENT: tuple[str, ...] = ("libs", "services", "db", "pyproject.toml", "uv.lock")
"""What `deploy/api.Dockerfile` copies, and therefore what makes two artifacts two.

The revisions are chosen by asking git which commits touched these paths rather
than by taking `HEAD` and `HEAD~1`, and that is not a convenience: the image is
content-addressed, so a commit that only edited a specification produces the
*same* digest — correctly. A rollback drill between two identical artifacts
would deploy one image twice and pass without proving anything.
"""

LIVE_PATH = "/healthz"
ALIVE = "alive"

CONTAINER_PORT = 8000
BUILD_TIMEOUT_S = 1800.0
START_TIMEOUT_S = 120.0
ANSWER_TIMEOUT_S = 15.0

UNRESOLVABLE = "unresolvable.invalid"

SERVICE_ENVIRONMENT: dict[str, str] = {
    "CANON_PROJECT": "ronin",
    "CANON_REPOSITORY_URL": f"https://{UNRESOLVABLE}/ronin.git",
    "CANON_REPOSITORY_BRANCH": "main",
    "CANON_REPOSITORY_CREDENTIAL": "unused-in-this-test",  # not-a-credential
    "CANON_FETCH_INTERVAL_S": "3600",
    "CANON_WEBHOOK_SECRET": "unused-in-this-test",  # not-a-credential
    "CANON_AUTH_ISSUER": f"https://{UNRESOLVABLE}",
    "CANON_AUTH_AUDIENCE": "cybercanon",
    "CANON_AUTH_KEY_SET_URL": f"https://{UNRESOLVABLE}/jwks.json",
    "CANON_AUTH_GROUP_ROLES": "canon-art=ART_DIRECTOR",
    "CANON_DATABASE_URL": f"postgresql://canon@{UNRESOLVABLE}:5432/canon",
    "CANON_OBJECT_STORE_URL": f"http://{UNRESOLVABLE}:9000/canon",
    "CANON_LINK_EXPIRY_S": "900",
    "CANON_WRITE_BACK_TIMEOUT_S": "30",
    "CANON_DRAIN_WINDOW_S": "60",
    "CANON_WORKING_COPIES": "/data/worktrees",
}
"""A complete configuration whose every dependency is unreachable.

The service refuses to start without one, and it must answer `/healthz` with
none of them reachable — which is the property the rollover depends on and the
reason a rollback can be asked whether it serves at all.
"""


@dataclass(frozen=True)
class Artifact:
    """One revision, and the digest the engine built it as."""

    revision: str
    digest: str


@dataclass(frozen=True)
class Released:
    """Two artifacts and the ledger that records them."""

    current: Artifact
    previous: Artifact
    ledger: Path


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _git(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=repo_root, capture_output=True, text=True, check=False
    )


def _extract(repo_root: Path, revision: str, into: Path) -> Path:
    """This revision's tree, on disk, with nothing of the working tree in it."""
    into.mkdir(parents=True, exist_ok=True)
    archived = subprocess.run(
        ["git", "archive", "--format=tar", revision],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    subprocess.run(["tar", "-x", "-C", str(into)], input=archived.stdout, check=True)
    return into


def _build(context: Path, tag: str) -> str:
    """Build that tree and answer the digest the engine recorded for the image."""
    subprocess.run(
        [
            ENGINE,
            "build",
            *REPRODUCIBLE,
            "--file",
            str(context / DOCKERFILE),
            "--tag",
            tag,
            str(context),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT_S,
    )
    inspected = subprocess.run(
        [ENGINE, "image", "inspect", tag, "--format", "{{.Id}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return inspected.stdout.strip()


def _record(repo_root: Path, ledger: Path, artifact: Artifact) -> None:
    """The pipeline's step, run the way `deploy/README.md` documents it."""
    recorded = subprocess.run(
        [
            sys.executable,
            "-m",
            "canon_release",
            "record",
            "--ledger",
            str(ledger),
            "--image",
            IMAGE,
            "--revision",
            artifact.revision,
            "--digest",
            artifact.digest,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=_tools_path(repo_root),
    )
    assert recorded.returncode == 0, recorded.stderr


def _withdraw(repo_root: Path, ledger: Path, revision: str) -> str:
    """`just release-rollback` — the digest to deploy, and nothing built."""
    printed = subprocess.run(
        [
            sys.executable,
            "-m",
            "canon_release",
            "rollback",
            "--ledger",
            str(ledger),
            "--image",
            IMAGE,
            "--revision",
            revision,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=_tools_path(repo_root),
    )
    assert printed.returncode == 0, printed.stderr
    return printed.stdout.strip()


def _tools_path(repo_root: Path) -> dict[str, str]:
    import os

    return os.environ | {"PYTHONPATH": str(repo_root / "tools")}


def _get(url: str, timeout: float = ANSWER_TIMEOUT_S) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            return int(answer.status), answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as refused:
        return int(refused.code), refused.read().decode("utf-8", "replace")


@dataclass
class Deployed:
    """A container running one digest, and where it answers."""

    name: str
    digest: str
    base_url: str


def _deploy(digest: str) -> Deployed:
    """Run that exact image. No tag, no context, nothing that could be built."""
    name = f"cybercanon-rollback-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    arguments = [ENGINE, "run", "--detach", "--name", name]
    for variable, value in SERVICE_ENVIRONMENT.items():
        arguments += ["--env", f"{variable}={value}"]
    arguments += ["--publish", f"127.0.0.1:{port}:{CONTAINER_PORT}", digest]
    subprocess.run(arguments, check=True, capture_output=True, text=True)
    deployed = Deployed(name=name, digest=digest, base_url=f"http://127.0.0.1:{port}")
    _await(deployed)
    return deployed


def _await(deployed: Deployed) -> None:
    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if not _running(deployed.name):  # pragma: no cover — only on a broken image
            raise AssertionError(f"the container exited: {_logs(deployed.name)}")
        try:
            _get(f"{deployed.base_url}{LIVE_PATH}", timeout=2.0)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.3)
            continue
        return
    raise AssertionError(  # pragma: no cover — only on a broken image
        f"the container never answered: {_logs(deployed.name)}"
    )


def _running(name: str) -> bool:
    inspected = subprocess.run(
        [ENGINE, "inspect", name, "--format", "{{json .State.Running}}"],
        capture_output=True,
        text=True,
    )
    return inspected.returncode == 0 and json.loads(inspected.stdout.strip() or "false")


def _image_of(name: str) -> str:
    """The image a running container was started from, as the engine records it."""
    inspected = subprocess.run(
        [ENGINE, "inspect", name, "--format", "{{.Image}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return inspected.stdout.strip()


def _logs(name: str) -> str:  # pragma: no cover — only on a failure
    printed = subprocess.run([ENGINE, "logs", "--tail", "40", name], capture_output=True, text=True)
    return f"{printed.stdout}{printed.stderr}"


def _remove(deployed: Deployed) -> None:
    subprocess.run([ENGINE, "rm", "--force", deployed.name], capture_output=True)


@pytest.fixture(scope="module")
def released(repo_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Released]:
    """Two revisions of this repository, built and recorded, contexts then removed."""
    if shutil.which(ENGINE) is None:  # pragma: no cover — machine dependent
        pytest.skip(NO_ENGINE)
    revisions = _revisions_changing_the_image(repo_root)
    if len(revisions) < 2:  # pragma: no cover — checkout dependent
        pytest.skip(NO_PREVIOUS)

    root = tmp_path_factory.mktemp("rollback")
    tags: list[str] = []
    built: list[Artifact] = []
    for revision in revisions:
        context = _extract(repo_root, revision, root / revision[:12])
        tag = f"cybercanon-api:rollback-{revision[:12]}"
        tags.append(tag)
        built.append(Artifact(revision=revision, digest=_build(context, tag)))
        shutil.rmtree(context)

    ledger = root / "digests.json"
    ledger.write_text("{}", encoding="utf-8")
    for artifact in built:
        _record(repo_root, ledger, artifact)

    try:
        yield Released(current=built[0], previous=built[1], ledger=ledger)
    finally:
        for tag in tags:
            subprocess.run([ENGINE, "image", "rm", "--force", tag], capture_output=True)


def _revisions_changing_the_image(repo_root: Path) -> tuple[str, ...]:
    """The two most recent revisions that changed what the image is built from.

    Newest first, so the first is N and the second is N-1. A commit that touched
    only a specification is skipped, because it produces the same artifact — the
    image is content-addressed, and a drill between two identical digests proves
    nothing about rolling back.
    """
    listed = _git(repo_root, "log", "-n", "2", "--format=%H", "--", *IMAGE_CONTENT)
    if listed.returncode != 0:  # pragma: no cover — checkout dependent
        return ()
    return tuple(line.strip() for line in listed.stdout.splitlines() if line.strip())


# --------------------------------------------------------------------------
# Deploy N, then N-1
# --------------------------------------------------------------------------


def test_two_revisions_build_to_two_distinct_artifacts(released: Released) -> None:
    """Without this the rest would pass while deploying one image twice."""
    assert released.current.digest != released.previous.digest


def test_revision_n_serves_when_it_is_deployed(released: Released) -> None:
    deployed = _deploy(released.current.digest)

    try:
        status, body = _get(f"{deployed.base_url}{LIVE_PATH}")

        assert (status, ALIVE in body) == (200, True), body
        assert _image_of(deployed.name) == released.current.digest
    finally:
        _remove(deployed)


def test_rolling_back_to_revision_n_minus_one_serves_the_previous_artifact(
    released: Released, repo_root: Path
) -> None:
    """The whole procedure: the ledger names a digest, and that digest is deployed.

    The build contexts were deleted by the fixture, so nothing here could have
    rebuilt anything even if it had tried — and the command that decides what to
    deploy only prints a digest, which is the point of it.
    """
    withdrawn = _withdraw(repo_root, released.ledger, released.previous.revision)

    assert withdrawn == released.previous.digest

    deployed = _deploy(withdrawn)
    try:
        status, body = _get(f"{deployed.base_url}{LIVE_PATH}")

        assert (status, ALIVE in body) == (200, True), body
        assert _image_of(deployed.name) == released.previous.digest
        assert _image_of(deployed.name) != released.current.digest
    finally:
        _remove(deployed)


def test_a_revision_the_ledger_does_not_hold_is_reported_rather_than_built(
    released: Released, repo_root: Path
) -> None:
    """*"An artifact nobody verified is not a rollback target."*"""
    refused = subprocess.run(
        [
            sys.executable,
            "-m",
            "canon_release",
            "rollback",
            "--ledger",
            str(released.ledger),
            "--image",
            IMAGE,
            "--revision",
            "0" * 40,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=_tools_path(repo_root),
    )

    assert refused.returncode != 0
    assert "no recorded digest" in refused.stderr
