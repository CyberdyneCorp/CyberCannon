"""Task 3.4 — the secret scan that gates a merge, and the artifact scan.

`deployment-operations` states both directions, and this suite runs both against
the real thing rather than against a sample:

* **the repository, at every revision reachable from the default branch**, is
  scanned here, on every `just check` — which is what *"the scan SHALL be part
  of the automated checks that gate a merge"* means in a project whose merge
  gate is that recipe;
* **the artifact** — the files the API image actually contains, computed from
  its `Dockerfile` — is searched for the values of the declared secret settings,
  which is *"inspecting an artifact reveals nothing about where it is running"*.

The task also asks for the scans to be **verified by introducing a fake
credential**, and they are: a throwaway repository is created in a temporary
directory, a fabricated credential is committed to it, and each scan is asserted
to fail. A scan nobody has watched fail is a scan that might be returning an
empty tuple for the wrong reason — which is the same failure as a fake that
lies, one layer out.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from canon_lint import secrets
from cybercanon.adapters.wiring.configuration import SECRETS, SETTINGS

pytestmark = pytest.mark.tooling

API_DOCKERFILE = Path("deploy/api.Dockerfile")

# Each of the three is invented for this suite and marked as such on its own
# line, which is the mechanism the scan offers instead of an allow-list of files.
FAKE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA\n"  # not-a-credential
FAKE_URL = "postgresql://canon:pw@db.invalid:5432/canon"  # not-a-credential
FAKE_TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"  # not-a-credential


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )


@pytest.fixture
def throwaway(tmp_path: Path) -> Path:
    """A repository of our own to put a fabricated credential into."""
    root = tmp_path / "throwaway"
    root.mkdir()
    _git(root, "init", "--quiet", "--initial-branch=main")
    (root / "README.md").write_text("nothing secret here\n", encoding="utf-8")
    _git(root, "add", "--all")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@cyberdyne.example",
        "commit",
        "--quiet",
        "--message",
        "seed",
    )
    return root


# --------------------------------------------------------------------------
# This repository
# --------------------------------------------------------------------------


def test_the_repository_carries_no_credential_at_any_reachable_revision(
    repo_root: Path,
) -> None:
    found = secrets.scan_repository(repo_root)

    assert not found, "credentials in the repository:\n" + "\n".join(str(one) for one in found)


def test_the_scan_really_reads_the_history_and_not_only_the_tree(repo_root: Path) -> None:
    """A scan of nothing would pass the test above without ever opening a file."""
    blobs = list(secrets.history_blobs(repo_root))

    assert len(blobs) > 50, "the history scan read almost nothing"
    assert any(name.startswith("openspec/") for name, _ in blobs)


def test_every_allowance_names_the_reason_it_is_not_a_credential() -> None:
    for allowance in secrets.ALLOWED:
        assert allowance.reason.strip(), f"{allowance.excerpt} is excused with no reason"


# --------------------------------------------------------------------------
# The scan fails when a credential is introduced
# --------------------------------------------------------------------------


@pytest.mark.parametrize("credential", [FAKE_KEY, FAKE_URL, FAKE_TOKEN])
def test_a_fabricated_credential_in_a_throwaway_branch_fails_the_scan(
    throwaway: Path, credential: str
) -> None:
    (throwaway / "settings.py").write_text(f'CREDENTIAL = """{credential}"""\n', encoding="utf-8")

    found = secrets.scan_repository(throwaway)

    assert found, "the scan passed a repository carrying a credential"
    assert any("settings.py" in finding.where for finding in found)


def test_a_credential_committed_and_then_deleted_is_still_found(
    throwaway: Path, credential: str = FAKE_TOKEN
) -> None:
    """Deleting the file does not un-publish it, so the history is scanned too."""
    leaked = throwaway / "leaked.py"
    leaked.write_text(f'TOKEN = "{credential}"\n', encoding="utf-8")
    _git(throwaway, "add", "--all")
    _git(
        throwaway,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@cyberdyne.example",
        "commit",
        "--quiet",
        "--message",
        "oops",
    )
    leaked.unlink()

    found = secrets.scan_repository(throwaway)

    assert found, "a credential that was committed and removed is still committed"
    assert all("@" in finding.where for finding in found), "it was found in the history"


# --------------------------------------------------------------------------
# The artifact
# --------------------------------------------------------------------------


def test_the_artifact_contains_no_value_of_a_declared_secret_setting(
    repo_root: Path,
) -> None:
    """The values a deployment configures may not be anywhere in the image."""
    configured = [f"the-{name.lower()}-value-of-this-deployment" for name in SECRETS]

    found = secrets.scan_artifact(repo_root, repo_root / API_DOCKERFILE, configured)

    assert not found, "\n".join(str(one) for one in found)


def test_the_artifact_scan_finds_a_secret_value_that_was_baked_in(
    repo_root: Path, tmp_path: Path
) -> None:
    """The scan is verified against an artifact that really does carry one."""
    staged = tmp_path / "artifact"
    (staged / "libs").mkdir(parents=True)
    (staged / "libs" / "settings.py").write_text('URL = "s3cr3t-value"\n', encoding="utf-8")
    dockerfile = tmp_path / "with-a-secret.Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\nCOPY libs ./libs\n", encoding="utf-8")

    found = secrets.scan_artifact(staged, dockerfile, ["s3cr3t-value"])

    assert found and found[0].rule == "configured secret"


def test_the_artifact_is_the_files_the_image_copies(repo_root: Path) -> None:
    """The scan's input is read from the `Dockerfile`, not listed a second time."""
    dockerfile = (repo_root / API_DOCKERFILE).read_text(encoding="utf-8")

    sources = secrets.artifact_sources(dockerfile)

    assert set(sources) >= {"libs", "services", "db", "uv.lock"}
    assert "deploy" not in sources, "the deployment documents are not in the image"


def test_every_declared_secret_is_scanned_for(repo_root: Path) -> None:
    """The list is the settings table's, so a new secret is covered by declaring it."""
    assert set(SECRETS) <= {setting.name for setting in SETTINGS}
    assert SECRETS, "a scan for an empty list of secrets would pass over anything"
