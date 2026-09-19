"""What was built, from which revision, and what is running where.

The specification asks three questions about a deployable artifact and they are
all questions about a *record* rather than about a build:

* *"a deployable artifact SHALL be built once per revision"* — so recording a
  second digest for a revision that already has one is **refused**. That refusal
  is the mechanism: a promotion that rebuilt would have to record a new digest,
  and it cannot;
* *"the digest of the running artifact SHALL equal the recorded digest"* —
  :func:`promotion` compares the two and names both when they differ, because
  "promotion failed" without the pair is a sentence nobody can act on;
* *"when the previous revision's recorded digest is deployed, no rebuild SHALL
  be required"* — :func:`rollback` answers with the digest to deploy, and says
  whether the ledger holds it. A revision the ledger does not know is the one
  case a rollback would need a build, and it is reported rather than performed.

The ledger is a file in the repository (`deploy/digests.json`), appended by the
build pipeline and read by the promotion check. A file rather than a query
against the platform, because the check has to be answerable from a checkout —
including on the day the platform is what is broken.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

LEDGER_PATH = Path("deploy/digests.json")
"""Where the record lives. Committed, because it is part of the revision."""

API = "api"
WEB = "web"
IMAGES: tuple[str, ...] = (API, WEB)
"""The two images. The index and the blob store are managed applications."""

DIGEST_PREFIX = "sha256:"


class AlreadyBuilt(Exception):
    """This revision was already built for this image, as a different digest.

    Raised rather than overwritten. *"An artifact SHALL be built once per
    revision and promoted between environments without rebuilding"*, so a second
    digest for one revision is not a record to keep — it is the rule being
    broken, and the build that produced it is the thing to stop.
    """

    def __init__(self, image: str, revision: str, recorded: str, offered: str) -> None:
        super().__init__(
            f"{image}@{revision} was built once already, as {recorded}; refusing to "
            f"record {offered}. An artifact is built once per revision and promoted."
        )
        self.image = image
        self.revision = revision
        self.recorded = recorded
        self.offered = offered


@dataclass(frozen=True)
class Build:
    """One artifact: the image, the revision it was built from, and its digest."""

    image: str
    revision: str
    digest: str
    built_at: str = ""

    @property
    def is_digest(self) -> bool:
        """Whether the digest is a content digest rather than a tag."""
        return self.digest.startswith(DIGEST_PREFIX) and len(self.digest) > len(DIGEST_PREFIX)

    def as_record(self) -> dict[str, str]:
        return {
            "image": self.image,
            "revision": self.revision,
            "digest": self.digest,
            "built_at": self.built_at,
        }


@dataclass(frozen=True)
class Ledger:
    """Every build this project has recorded, oldest first."""

    builds: tuple[Build, ...] = ()

    @staticmethod
    def loads(text: str) -> Ledger:
        recorded = json.loads(text or "[]")
        return Ledger(tuple(Build(**entry) for entry in recorded))

    @staticmethod
    def read(path: Path = LEDGER_PATH) -> Ledger:
        return Ledger.loads(path.read_text(encoding="utf-8") if path.is_file() else "[]")

    def dumps(self) -> str:
        return json.dumps([build.as_record() for build in self.builds], indent=2) + "\n"

    def write(self, path: Path = LEDGER_PATH) -> None:
        path.write_text(self.dumps(), encoding="utf-8")

    def record(self, build: Build) -> Ledger:
        """This ledger with that build in it, or a refusal if it was built already."""
        recorded = self.digest_for(build.image, build.revision)
        if recorded and recorded != build.digest:
            raise AlreadyBuilt(build.image, build.revision, recorded, build.digest)
        if recorded:
            return self
        return replace(self, builds=(*self.builds, build))

    def digest_for(self, image: str, revision: str) -> str:
        """What that revision of that image was built as, or an empty string."""
        for build in self.builds:
            if build.image == image and build.revision == revision:
                return build.digest
        return ""

    def revisions_of(self, image: str) -> tuple[str, ...]:
        """Every revision recorded for that image, in the order it was built."""
        return tuple(build.revision for build in self.builds if build.image == image)

    def previous(self, image: str, revision: str) -> str:
        """The revision built before that one — what a rollback deploys."""
        revisions = self.revisions_of(image)
        if revision not in revisions:
            return ""
        position = revisions.index(revision)
        return revisions[position - 1] if position else ""


@dataclass(frozen=True)
class Promotion:
    """What an environment is running, against what the revision was built as."""

    image: str
    revision: str
    environment: str
    recorded: str
    running: str

    @property
    def conforms(self) -> bool:
        return bool(self.recorded) and self.recorded == self.running

    @property
    def reason(self) -> str:
        """Why it does not conform, naming both digests. Empty when it does."""
        if self.conforms:
            return ""
        if not self.recorded:
            return (
                f"{self.image}@{self.revision} has no recorded digest, so what "
                f"{self.environment} is running was never verified anywhere"
            )
        return (
            f"{self.environment} is running {self.running or 'nothing'} for "
            f"{self.image}@{self.revision}, which was built as {self.recorded}: "
            "the artifact was rebuilt rather than promoted"
        )


def promotion(
    ledger: Ledger, *, image: str, revision: str, environment: str, running: str
) -> Promotion:
    """Whether what that environment is running is the artifact that was built."""
    return Promotion(
        image=image,
        revision=revision,
        environment=environment,
        recorded=ledger.digest_for(image, revision),
        running=running,
    )


def promotions(
    ledger: Ledger, *, image: str, revision: str, running: dict[str, str]
) -> tuple[Promotion, ...]:
    """One verdict per environment, in a deterministic order."""
    return tuple(
        promotion(ledger, image=image, revision=revision, environment=where, running=digest)
        for where, digest in sorted(running.items())
    )


@dataclass(frozen=True)
class Rollback:
    """The artifact a withdrawal deploys, and whether it has to be built first."""

    image: str
    revision: str
    digest: str

    @property
    def requires_build(self) -> bool:
        """True only when the ledger does not hold that revision — the one bad case."""
        return not self.digest


def rollback(ledger: Ledger, *, image: str, revision: str) -> Rollback:
    """The recorded digest for the revision being rolled back to."""
    return Rollback(image=image, revision=revision, digest=ledger.digest_for(image, revision))


__all__ = [
    "API",
    "IMAGES",
    "LEDGER_PATH",
    "WEB",
    "AlreadyBuilt",
    "Build",
    "Ledger",
    "Promotion",
    "Rollback",
    "promotion",
    "promotions",
    "rollback",
]
