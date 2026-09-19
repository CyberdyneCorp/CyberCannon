"""A hosted project on disk: a real remote, a real working copy, real bytes.

Groups 6 and 7 both need the same thing and neither can use a fake for it. The
index rebuild is specified as *"rebuilt from the working copy"*, and the blob
mirror is specified as re-mirroring *"from its working copy"* — so a suite that
rebuilt from a dictionary would be asserting that a dictionary round-trips.

The corpus is deliberately wider than the one `test_hosted_working_copy` uses,
because these two groups are about content the specification files *point at*
rather than about the files themselves: two assets with concept views, one of
them sharing an image with the other, plus an export. The shared image is the
interesting one — content addressing says two assets referencing the same bytes
store once, and a corpus where every file is unique could not tell.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cybercanon.adapters.outbound.git.repository_host import GitRepositoryHost, ProjectRemote
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore

PROJECT = "ronin"
BRANCH = "main"

SCOUT_SPEC = "characters/mech_scout/asset.yaml"
MULE_SPEC = "vehicles/mule/asset.yaml"

SCOUT_FRONT = "characters/mech_scout/concept/front.png"
SCOUT_SHARED = "characters/mech_scout/concept/palette.png"
MULE_SHARED = "vehicles/mule/concept/palette.png"
SCOUT_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"

PALETTE = b"\x89PNG\r\n\x1a\nthe studio palette, shared by both assets"
FRONT = b"\x89PNG\r\n\x1a\nthe scout mech, front elevation"
EXPORT = b"glTF\x02\x00\x00\x00the scout mech, exported"

PROJECT_CONFIG = b"""\
schema_version: 1
name: ronin
"""

SCOUT = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
aliases: [drone, scout]
owner_art: rafa@cyberdyne.com
owner_design: ana@cyberdyne.com
concept:
  views:
    - {SCOUT_FRONT}
    - {SCOUT_SHARED}
links:
  source: art/source/mech_scout.blend
  engine: Content/Ronin/Characters/MechScout
""".encode()

MULE = f"""\
schema_version: 1
id: mule
name: Mule Hauler
status: concept
owner_art: rafa@cyberdyne.com
concept:
  views:
    - {MULE_SHARED}
""".encode()

CORPUS: dict[str, bytes] = {
    ".canon/project.yaml": PROJECT_CONFIG,
    SCOUT_SPEC: SCOUT,
    MULE_SPEC: MULE,
    SCOUT_FRONT: FRONT,
    SCOUT_SHARED: PALETTE,
    MULE_SHARED: PALETTE,
    SCOUT_EXPORT: EXPORT,
}
"""Two assets, three views, one export — and one image referenced twice."""


@dataclass(frozen=True)
class Staged:
    """A project's bare remote and the host that serves a working copy of it."""

    host: GitRepositoryHost
    bare: Path
    home: Path
    root: Path

    @property
    def working_copy(self) -> Path:
        return self.host.path(PROJECT)

    def spec_store(self) -> GitSpecStore:
        return GitSpecStore(self.working_copy)

    def commit_outside(self, path: str, content: bytes | None, message: str = "outside") -> None:
        """Somebody commits straight to the repository, past this service."""
        scratch = self.root / "outside"
        if not scratch.exists():
            git(None, ["clone", "--quiet", str(self.bare), str(scratch)], self.home)
        git(scratch, ["fetch", "--quiet", "origin", BRANCH], self.home)
        git(scratch, ["reset", "--quiet", "--hard", f"origin/{BRANCH}"], self.home)
        target = scratch / path
        if content is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        commit(scratch, message, self.home)
        git(scratch, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"], self.home)


def stage(tmp_path: Path, files: dict[str, bytes] | None = None) -> Staged:
    """A seeded bare remote and a host configured for it. Nothing is cloned yet."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    bare = tmp_path / "remote.git"
    git(None, ["init", "--quiet", "--bare", f"--initial-branch={BRANCH}", str(bare)], home)
    seed = tmp_path / "seed"
    git(None, ["clone", "--quiet", str(bare), str(seed)], home)
    for path, content in (CORPUS if files is None else files).items():
        target = seed / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    commit(seed, "seed the project", home)
    git(seed, ["push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}"], home)
    host = GitRepositoryHost(
        tmp_path / "working-copies",
        [ProjectRemote(project=PROJECT, url=str(bare), branch=BRANCH)],
        environment={"HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    return Staged(host=host, bare=bare, home=home, root=tmp_path)


def ready(tmp_path: Path, files: dict[str, bytes] | None = None) -> Staged:
    """A staged project whose working copy has been obtained."""
    staged = stage(tmp_path, files)
    staged.host.clone(PROJECT)
    return staged


def git(root: Path | None, arguments: Sequence[str], home: Path) -> str:
    """One git command, isolated from whatever this machine's git is configured to do."""
    located = ["-C", str(root)] if root is not None else []
    completed = subprocess.run(
        ["git", *located, *arguments],
        check=True,
        capture_output=True,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )
    return completed.stdout.decode("utf-8", errors="replace")


def commit(root: Path, message: str, home: Path) -> None:
    git(root, ["add", "--all"], home)
    git(
        root,
        [
            "-c",
            "user.name=Seed",
            "-c",
            "user.email=seed@cyberdyne.example",
            "commit",
            "--quiet",
            "--allow-empty",
            "--message",
            message,
        ],
        home,
    )


__all__ = [
    "BRANCH",
    "CORPUS",
    "EXPORT",
    "FRONT",
    "MULE_SHARED",
    "MULE_SPEC",
    "PALETTE",
    "PROJECT",
    "SCOUT_EXPORT",
    "SCOUT_FRONT",
    "SCOUT_SHARED",
    "SCOUT_SPEC",
    "Staged",
    "commit",
    "git",
    "ready",
    "stage",
]
