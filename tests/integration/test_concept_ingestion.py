"""Group 3 and task 7.5 — the real adapters, real git, and the two surfaces agreeing.

Three things can only be checked against real files and a real repository, and
each is a requirement rather than a nicety:

* **format comes from the content** — a TIFF whose file name ends in `.png` has
  to be reported as a TIFF by the reader that will actually read it (task 3.1);
* **derivation is deterministic** — two runs over the same committed image have
  to produce the same content hashes, or a wiped thumbnail cache cannot be
  rebuilt onto the keys it had (task 3.2);
* **`canon add-view` and the ingestion endpoint produce the same commit** — the
  founding rule of this product applied to the first feature an artist touches
  (task 7.5). They run the same use case over the same port, and the only way to
  know that is to run both and compare what landed in two real repositories.
"""

from __future__ import annotations

import json
import shutil
from base64 import b64encode
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from canon_fixtures import image as fixtures
from cybercanon.adapters.inbound.cli.app import build_app as build_cli
from cybercanon.adapters.inbound.http.app import build_app as build_api
from cybercanon.adapters.inbound.http.surface import HostedProject, Surface
from cybercanon.adapters.inbound.http.versioning import VERSION
from cybercanon.adapters.outbound.git import commands
from cybercanon.adapters.outbound.git.local_host import LocalRepositoryHost
from cybercanon.adapters.outbound.image.inspector import PillowImageInspector
from cybercanon.adapters.outbound.image.thumbnails import PillowThumbnailRenderer
from cybercanon.adapters.wiring.build import build_container
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.image_inspector import ImageUnreadable
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.domain.identity import Actor, ActorId, Role

pytestmark = pytest.mark.integration

PROJECT = "ronin"
SCOUT = "mech_scout"
SCOUT_DIR = f"characters/{SCOUT}"
FRONT = f"{SCOUT_DIR}/concept/front.png"

RAFA_NAME = "Rafa"
RAFA_EMAIL = "rafa@cyberdyne.com"
TOKEN = "a-verified-token"

PROJECT_CONFIG = f"schema_version: 1\nname: {PROJECT}\n"
ASSET = f"schema_version: 1\nid: {SCOUT}\nname: Scout Mech\nstatus: concept\n"
ACTORS = f"""\
schema_version: 1
actors:
  - subject: local
    display_name: {RAFA_NAME}
    emails: [{RAFA_EMAIL}]
  - subject: auth|rafa
    display_name: {RAFA_NAME}
    emails: [{RAFA_EMAIL}]
"""

ENVIRONMENT = {"HOME": "", "GIT_CONFIG_GLOBAL": "/dev/null"}


def a_checkout(root: Path) -> Path:
    """A real git working copy holding one asset, its project file and its mapping."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, ["init", "--quiet", "--initial-branch=main"])
    _git(root, ["config", "user.name", "Seed"])
    _git(root, ["config", "user.email", "seed@cyberdyne.example"])
    for path, text in (
        (".canon/project.yaml", PROJECT_CONFIG),
        (".canon/actors.yaml", ACTORS),
        (f"{SCOUT_DIR}/asset.yaml", ASSET),
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(root, ["add", "--all"])
    _git(root, ["commit", "--quiet", "--message", "seed"])
    return root


def _git(root: Path, arguments: list[str]) -> None:
    completed = commands.run(root, arguments, environment={"GIT_CONFIG_GLOBAL": "/dev/null"})
    assert completed.ok, completed.err


def _show(root: Path, revision: str, path: str) -> bytes:
    completed = commands.run(root, ["cat-file", "-p", f"{revision}:{path}"])
    assert completed.ok, completed.err
    return completed.out


def _log(root: Path, fmt: str) -> str:
    completed = commands.run(root, ["log", "-1", f"--format={fmt}"])
    assert completed.ok, completed.err
    return completed.text.strip()


# --------------------------------------------------------------------------
# 3.1 — the format comes from the content
# --------------------------------------------------------------------------


def test_a_tiff_written_as_png_is_read_as_a_tiff(tmp_path: Path) -> None:
    """The file is called `front.png`. It is a TIFF, and the reader says so."""
    path = fixtures.write_image(tmp_path / "front.png", fixtures.TIFF, 320, 240)

    facts = PillowImageInspector().inspect(path.read_bytes(), name=path.name)

    assert facts.format == "tiff"
    assert (facts.width, facts.height) == (320, 240)


def test_a_file_that_is_not_an_image_is_refused_by_name(tmp_path: Path) -> None:
    path = tmp_path / "notes.png"
    path.write_bytes(fixtures.not_an_image())

    with pytest.raises(ImageUnreadable) as refusal:
        PillowImageInspector().inspect(path.read_bytes(), name=path.name)

    assert "notes.png" in str(refusal.value)


# --------------------------------------------------------------------------
# 3.2 — derivation is deterministic
# --------------------------------------------------------------------------


def test_two_derivations_of_one_image_produce_identical_content_hashes(tmp_path: Path) -> None:
    path = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 1024, 768)
    renderer = PillowThumbnailRenderer()

    first = renderer.derive(path.read_bytes())
    second = renderer.derive(path.read_bytes())

    assert [thumbnail.digest for thumbnail in first] == [thumbnail.digest for thumbnail in second]
    assert all(thumbnail.content_type == "image/webp" for thumbnail in first)


def test_a_thumbnail_fits_inside_the_size_it_was_asked_for(tmp_path: Path) -> None:
    path = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 1024, 768)

    (thumbnail,) = PillowThumbnailRenderer().derive(path.read_bytes(), (256,))

    assert max(thumbnail.width, thumbnail.height) <= 256
    assert thumbnail.width / thumbnail.height == pytest.approx(1024 / 768, rel=0.02)


# --------------------------------------------------------------------------
# The local host over real git
# --------------------------------------------------------------------------


def test_the_local_host_reads_the_history_of_a_path_out_of_real_git(tmp_path: Path) -> None:
    root = a_checkout(tmp_path / "checkout")
    host = LocalRepositoryHost(root, PROJECT)
    for index in (1, 2):
        (root / f"{SCOUT_DIR}/asset.yaml").write_text(ASSET + f"# {index}\n", encoding="utf-8")
        _git(root, ["add", "--all"])
        _git(root, ["commit", "--quiet", "--message", f"edit {index}"])

    history = host.history(PROJECT, f"{SCOUT_DIR}/asset.yaml")

    assert len(history.revisions) == 3
    assert history.is_complete
    assert history.revisions[0].content is not None
    assert history.revisions[0].byte_size > 0


def test_the_local_host_pushes_nothing_and_answers_the_local_head(tmp_path: Path) -> None:
    """`canon` does not own the checkout, so a push is a no-op that cannot fail."""
    root = a_checkout(tmp_path / "checkout")
    host = LocalRepositoryHost(root, PROJECT)

    assert host.push(PROJECT) == host.head(PROJECT)
    assert host.recover(PROJECT).discarded == ()


# --------------------------------------------------------------------------
# 7.5 — the two surfaces produce the same commit
# --------------------------------------------------------------------------


def _through_the_command_line(root: Path, image: Path) -> None:
    container = build_container(root, environment={})
    result = CliRunner().invoke(
        build_cli(container), ["add-view", SCOUT, str(image), "--slot", "front"]
    )
    assert result.exit_code == 0, result.output


def _through_the_api(root: Path, image: Path) -> None:
    container = replace(build_container(root, environment={}), project_id=PROJECT)
    provider = InMemoryIdentityProvider()
    provider.add(
        Credential(TOKEN),
        Actor(
            id=ActorId("auth|rafa"),
            display_name=RAFA_NAME,
            roles=(Role.ARTIST,),
            projects=(PROJECT,),
        ),
    )
    surface = Surface(
        projects={
            PROJECT: HostedProject(
                name=PROJECT,
                container=container,
                repository_host=LocalRepositoryHost(root, PROJECT),
            )
        },
        identity_provider=provider,
        image_inspector=PillowImageInspector(),
        thumbnail_renderer=PillowThumbnailRenderer(),
    )
    client = TestClient(build_api(surface=surface))
    response = client.post(
        f"/{VERSION}/projects/{PROJECT}/assets/{SCOUT}/views",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "images": [
                {
                    "slot": "front",
                    "content": b64encode(image.read_bytes()).decode("ascii"),
                    "filename": image.name,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text


def test_the_command_line_and_the_http_surface_produce_identical_commits(tmp_path: Path) -> None:
    """The founding rule, applied to the first feature an artist touches.

    Two real repositories, the same image, one surface each. What is compared is
    everything a reviewer would see — the message, the author address, the paths
    and the committed bytes — because *"it passed on my machine but the site
    says it failed"* is the class of bug this product exists to prevent, and a
    view is the first thing both surfaces write.

    The author **address** is what is compared and not the display name, because
    the two surfaces are resolving two different subjects here: the command line
    is the local unauthenticated actor and the endpoint is a verified `auth|`
    subject, and `.canon/actors.yaml` binds both to the same person. The address
    is the identity `git blame` answers with; the name that travels beside it is
    whatever the resolution chain called the actor.
    """
    image = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 1024, 768)
    by_cli = a_checkout(tmp_path / "by-cli")
    by_api = a_checkout(tmp_path / "by-api")

    _through_the_command_line(by_cli, image)
    _through_the_api(by_api, image)

    assert _log(by_cli, "%s") == _log(by_api, "%s")
    assert _log(by_cli, "%ae") == _log(by_api, "%ae") == RAFA_EMAIL
    assert _show(by_cli, "HEAD", FRONT) == _show(by_api, "HEAD", FRONT) == image.read_bytes()
    assert _names(by_cli) == _names(by_api) == (FRONT,)


def _names(root: Path) -> tuple[str, ...]:
    completed = commands.run(root, ["show", "--name-only", "--format=", "HEAD"])
    assert completed.ok, completed.err
    return tuple(line.strip() for line in completed.lines if line.strip())


def test_the_command_line_commits_into_the_checkout_and_pushes_nothing(tmp_path: Path) -> None:
    root = a_checkout(tmp_path / "checkout")
    image = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 800, 600)

    _through_the_command_line(root, image)

    assert (root / FRONT).read_bytes() == image.read_bytes()
    assert commands.run(root, ["remote"]).text.strip() == ""


def test_the_projects_declared_limits_reach_the_upload(tmp_path: Path) -> None:
    """Task 1.3 end to end: `.canon/project.yaml` says WebP only, and PNG is refused."""
    root = a_checkout(tmp_path / "checkout")
    (root / ".canon/project.yaml").write_text(
        PROJECT_CONFIG + "ingestion:\n  accepted_formats: [webp]\n  max_dimension: 512\n",
        encoding="utf-8",
    )
    _git(root, ["add", "--all"])
    _git(root, ["commit", "--quiet", "--message", "declare the ingestion limits"])
    image = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 800, 600)

    container = build_container(root, environment={})
    result = CliRunner().invoke(
        build_cli(container), ["add-view", SCOUT, str(image), "--slot", "front"]
    )

    assert result.exit_code != 0
    assert "webp" in result.output
    assert not (root / FRONT).exists()


def test_the_mirror_rebuilds_from_the_repository_onto_the_same_keys(tmp_path: Path) -> None:
    """Task 3.5, against a real checkout: drop the mirror, run the command, compare."""
    root = a_checkout(tmp_path / "checkout")
    image = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 800, 600)
    _through_the_command_line(root, image)
    container = build_container(root, environment={})
    before = container.rebuild_view_mirror()
    assert before.value.keys, before
    shutil.rmtree(root / ".canon" / "blobs", ignore_errors=True)

    after = container.rebuild_view_mirror()

    assert after.value.keys == before.value.keys
    assert after.value.thumbnails == before.value.thumbnails > 0


def test_canon_views_rebuild_reports_what_it_mirrored(tmp_path: Path) -> None:
    """The command a person runs, through the same use case the container exposes."""
    root = a_checkout(tmp_path / "checkout")
    image = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 800, 600)
    _through_the_command_line(root, image)

    result = CliRunner().invoke(
        build_cli(build_container(root, environment={})), ["views", "rebuild", "--json"]
    )

    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert document["mirrored"] == 1
    assert document["thumbnails"] == 2
    assert list(document["keys"]) == [FRONT]


def test_no_thumbnail_reaches_the_working_copy(tmp_path: Path) -> None:
    """D9, over a real checkout: there is no path in the renderer's signature."""
    root = a_checkout(tmp_path / "checkout")
    image = fixtures.write_image(tmp_path / "front.png", fixtures.PNG, 800, 600)

    _through_the_command_line(root, image)

    concept = sorted(path.name for path in (root / SCOUT_DIR / "concept").iterdir())
    assert concept == ["front.png"]
    assert _names(root) == (FRONT,)
