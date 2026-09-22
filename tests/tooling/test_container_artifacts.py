"""Tasks 3.1-3.2 — the two images, and what may not be in them.

`deployment-operations`: *"artifacts SHALL be free of environment-specific
values, so that inspecting an artifact reveals nothing about where it is
running"*, and *"a deployable artifact SHALL be built once per revision and
promoted between environments without rebuilding"*. Both are properties of the
`Dockerfile`, and they are asserted by reading it rather than by trusting a
comment inside it:

* **nothing environment-specific at build time.** No `ARG` or `ENV` carrying a
  `CANON_` setting, no endpoint of ours, no `.env` copied in. The image cannot
  tell which environment it is in, which is what makes a digest verified in
  pre-production mean something in production;
* **the environment comes from the committed lock files**, with `--frozen` on
  both halves, so two builds of one revision resolve identically;
* **the API image serves and does not migrate** (D4, task 4.4). Migrations are a
  release step; an entry point that ran them would run them once per instance;
* **the web image runs the node adapter** (D10), because its readiness must be
  this process's own answer rather than the API's;
* **the build context carries nothing environment-specific either.** Reading the
  two `Dockerfile`s is not enough on its own: the web image copies a whole
  directory, and SvelteKit reads a `.env` sitting in it at build time. What is
  *not sent to the engine* is therefore part of the same property, and
  `.dockerignore` is where it is stated.

The one assertion that needs a container engine — *build it twice and compare
the digests* — is skipped where there is none, and says so. A test that reported
green because it built nothing would be worse than one that does not run.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from cybercanon.adapters.wiring.configuration import PREFIX, SETTINGS

pytestmark = pytest.mark.tooling

API = Path("deploy/api.Dockerfile")
WEB = Path("deploy/web.Dockerfile")
CONTEXT = Path(".dockerignore")

DECLARED = re.compile(r"^(?:ARG|ENV)\s+(?P<body>.+)$", re.MULTILINE)
COMMENT = re.compile(r"^\s*#.*$", re.MULTILINE)

RUNTIME_ONLY = {"PATH", "PYTHONUNBUFFERED", "HOST", "PORT", "NODE_ENV"}
"""The only build-time values either image may carry: none of them is a setting."""

OUR_HOSTS = ("coolify.cyberdynecorp.ai", "cyberdynecorp.ai", "amini", "minio:", "postgres:")
"""Anything naming where a deployment is. An image that knew one would be one."""


@pytest.fixture(scope="module")
def api(repo_root: Path) -> str:
    return (repo_root / API).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def web(repo_root: Path) -> str:
    return (repo_root / WEB).read_text(encoding="utf-8")


def instructions(dockerfile: str) -> str:
    """The `Dockerfile` with its commentary removed — what actually builds."""
    return COMMENT.sub("", dockerfile)


def declared_names(dockerfile: str) -> set[str]:
    """Every name an `ARG` or `ENV` sets in this image."""
    return {
        entry.split("=", 1)[0].strip()
        for match in DECLARED.finditer(instructions(dockerfile))
        for entry in [match.group("body").split(" ")[0]]
    }


# --------------------------------------------------------------------------
# 3.1 — the API image
# --------------------------------------------------------------------------


@pytest.mark.parametrize("image", ["api", "web"])
def test_no_setting_is_baked_into_an_image(image: str, api: str, web: str) -> None:
    dockerfile = api if image == "api" else web

    baked = {name for name in declared_names(dockerfile) if name.startswith(PREFIX)}

    assert not baked, f"{image} bakes configuration into the artifact: {sorted(baked)}"


@pytest.mark.parametrize("image", ["api", "web"])
def test_an_image_declares_nothing_but_runtime_values(image: str, api: str, web: str) -> None:
    dockerfile = api if image == "api" else web

    assert declared_names(dockerfile) <= RUNTIME_ONLY


@pytest.mark.parametrize("image", ["api", "web"])
def test_no_image_names_a_deployment_of_ours(image: str, api: str, web: str) -> None:
    """*"Inspecting an artifact reveals nothing about where it is running."*"""
    built = instructions(api if image == "api" else web).lower()

    assert not [host for host in OUR_HOSTS if host in built]


@pytest.mark.parametrize("image", ["api", "web"])
def test_no_image_copies_an_environment_file(image: str, api: str, web: str) -> None:
    """No file fallback means there is no file to fall back to, either."""
    built = instructions(api if image == "api" else web)

    assert ".env" not in built
    assert "deploy/" not in built, "the deployment documents are not part of the artifact"


def test_the_api_image_installs_from_the_committed_lock_file(api: str) -> None:
    """Two builds of one revision resolve to identical versions, or promotion is a lie."""
    assert "uv sync --frozen" in api
    assert "uv.lock" in api


def test_the_api_image_serves_and_does_not_migrate(api: str) -> None:
    """D4: migrations are a release step, so no instance runs one at start."""
    started = instructions(api)[instructions(api).index("CMD") :]

    assert "cybercanon.api.migrate" not in started
    assert "cybercanon.api" in started


def test_the_api_image_declares_the_working_copy_volume(api: str) -> None:
    """D6's one piece of owned state, named in the artifact that mounts it."""
    assert "/data/worktrees" in api


# --------------------------------------------------------------------------
# 3.2 — the web image
# --------------------------------------------------------------------------


def test_the_web_image_runs_the_server_runtime(web: str) -> None:
    """D10: the node adapter, because readiness is this process's own answer."""
    assert 'CMD ["node", "build"]' in web


def test_the_web_image_installs_from_the_committed_lock_file(web: str) -> None:
    assert "pnpm install --frozen-lockfile" in web
    assert "pnpm-lock.yaml" in web


def test_the_web_image_carries_no_client_secret(web: str) -> None:
    """The browser client signs in with a proof key; a secret here would be published."""
    built = instructions(web).upper()

    assert "CLIENT_SECRET" not in built


def test_the_web_image_needs_no_api_to_build(web: str) -> None:
    """A build that called the API would be a build that needs an environment."""
    assert "PUBLIC_CANON_API_URL" not in instructions(web)


# --------------------------------------------------------------------------
# 3.1-3.2 — the build context, which is the other half of "nothing
# environment-specific at build time"
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ignored(repo_root: Path) -> tuple[str, ...]:
    """The `.dockerignore` patterns: what is never sent to the engine."""
    path = repo_root / CONTEXT
    assert path.is_file(), (
        f"{CONTEXT} is what keeps an environment-specific file out of a build. "
        "The web image copies a whole directory, and a `.env` in it is read by "
        "the build — so without this file the property is a hope."
    )
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def _matches(pattern: str, candidate: str) -> bool:
    """One `.dockerignore` pattern against one path, with `**/` at any depth."""
    if pattern.startswith("**/"):
        parts = candidate.split("/")
        tail = pattern[3:]
        return any(fnmatch.fnmatch("/".join(parts[at:]), tail) for at in range(len(parts)))
    return fnmatch.fnmatch(candidate, pattern)


def excluded(patterns: tuple[str, ...], path: str) -> bool:
    """Whether that path is kept out of the context — itself or by an ancestor."""
    parts = path.split("/")
    ancestors = ["/".join(parts[: at + 1]) for at in range(len(parts))]
    return any(_matches(pattern, one) for pattern in patterns for one in ancestors)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "apps/cybercanon/web/.env",
        "apps/cybercanon/web/.env.production",
        "apps/cybercanon/web/.env.local",
        "services/cybercanon/api/.env",
        "deploy/production.key",
    ],
)
def test_no_environment_file_reaches_a_build(ignored: tuple[str, ...], path: str) -> None:
    """The one that would actually bite: SvelteKit reads a `.env` at build time."""
    assert excluded(ignored, path), (
        f"{path} would be sent to the engine and could be baked into a promoted "
        "artifact. An image may not be able to tell which environment it is in."
    )


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        ".venv/bin/python",
        "apps/cybercanon/web/node_modules/@sveltejs/kit/package.json",
        "libs/cybercanon/domain/__pycache__/asset.cpython-312.pyc",
        "apps/cybercanon/web/build/index.js",
        "apps/cybercanon/web/.svelte-kit/output/server/index.js",
    ],
)
def test_no_machine_state_reaches_a_build(ignored: tuple[str, ...], path: str) -> None:
    """An image builds from a revision, not from somebody's checkout."""
    assert excluded(ignored, path)


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "uv.lock",
        "libs/cybercanon/domain/asset.py",
        "services/cybercanon/api/main.py",
        "db/migrations/0001_index.sql",
        "apps/cybercanon/web/package.json",
        "apps/cybercanon/web/pnpm-lock.yaml",
        "apps/cybercanon/web/.npmrc",
        "apps/cybercanon/web/src/routes/readyz/+server.ts",
    ],
)
def test_everything_the_images_copy_still_reaches_the_build(
    ignored: tuple[str, ...], path: str
) -> None:
    """The guard on the guard: an over-broad pattern breaks the build instead."""
    assert not excluded(ignored, path)


def test_the_matcher_itself_discriminates() -> None:
    """A matcher that answered true for everything would pass the suite above."""
    assert _matches("**/.env", "apps/web/.env")
    assert _matches("**/.env", ".env")
    assert not _matches("**/.env", "apps/web/.npmrc")
    assert _matches("apps/cybercanon/web/build", "apps/cybercanon/web/build")
    assert not _matches("apps/cybercanon/web/build", "apps/cybercanon/web/src")


# --------------------------------------------------------------------------
# The settings table is the list of what may not be baked in
# --------------------------------------------------------------------------


def test_the_check_covers_every_declared_setting() -> None:
    """A new setting is covered by declaring it, not by editing this suite."""
    assert all(setting.name.startswith(PREFIX) for setting in SETTINGS)


# --------------------------------------------------------------------------
# The reproducibility assertion, where there is an engine to build with
# --------------------------------------------------------------------------

ENGINE = "docker"
NO_ENGINE = (
    "no container engine on this machine: `docker` is what builds the artifact, "
    "and a digest comparison with nothing built would assert nothing"
)


def _build(repo_root: Path, dockerfile: Path, tag: str) -> str:
    """Build the image and answer the digest the engine recorded for it."""
    subprocess.run(
        [ENGINE, "build", "--file", str(dockerfile), "--tag", tag, "."],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    built = subprocess.run(
        [ENGINE, "image", "inspect", tag, "--format", "{{.Id}}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return built.stdout.strip()


@pytest.mark.skipif(shutil.which(ENGINE) is None, reason=NO_ENGINE)
def test_building_one_revision_twice_produces_one_digest(repo_root: Path) -> None:
    """*"Built once per revision and promoted"* is only safe if a rebuild agrees."""
    first = _build(repo_root, repo_root / API, "cybercanon-api:reproducibility-1")
    second = _build(repo_root, repo_root / API, "cybercanon-api:reproducibility-2")

    assert first == second
