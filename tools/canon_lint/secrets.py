"""The secret scan that gates a merge, and the artifact scan beside it.

`deployment-operations` asks for two scans and they answer different questions:

* *"the repository is scanned for credentials at any revision reachable from the
  default branch"*, and the scan *"SHALL be part of the automated checks that
  gate a merge"* — so it runs under `just check` like everything else, over the
  working tree **and** over every blob in the history. A credential that was
  committed and then deleted is still published; the fix is a rotation, and a
  scan that only read the current tree would never say so;
* *"a deployable artifact ... its contents are searched for the values of the
  declared secret settings"* — a different question with a different input: the
  files the image actually contains, against the values this deployment
  configures. It is what makes *"inspecting an artifact reveals nothing about
  where it is running"* checkable rather than asserted.

**Why these rules and not a generic entropy scan.** Every rule below matches a
credential *shape* that is issued by something: a PEM block, an AWS key id, a
GitHub or Slack token, a URL with an inline password, a signed token. Those have
almost no false positives and catch the ways a credential actually reaches a
repository. The tempting extra rule — *anything assigned to a name containing
`password`* — would fire on every test fixture in this repository and on the
settings table itself, and a scan that fires constantly is a scan somebody turns
off. A high-entropy string that matches none of these is invisible here, which
is the trade this makes deliberately.

**Two ways to excuse a match, and neither of them is a path.** A path allowance
turns into a hole the day somebody puts a real credential in that file, so:

* a line carrying the marker `not-a-credential` is excused **where it is
  written**, in review, beside the fabricated string it is about. That is how a
  test fixture, a documented example or this module's own rules say so;
* :data:`ALLOWED` excuses one exact fabricated string wherever it appears,
  which is what the *history* needs: a marker cannot be added to a revision that
  was already made, and the scan reads those too.

Every allowance carries a reason, and `tests/tooling/test_secret_scan.py` fails
if one does not.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

NULL = b"\x00"
"""What tells a blob apart from text without guessing at an encoding."""

MAX_BYTES = 2_000_000
"""Nothing larger is text this scan can read, and a mesh is not a credential."""


@dataclass(frozen=True)
class Rule:
    """One credential shape, and what an operator does about a match."""

    name: str
    pattern: re.Pattern[str]
    what: str


@dataclass(frozen=True)
class Finding:
    """One match: where it is, which rule found it, and what it looks like."""

    where: str
    line: int
    rule: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.where}:{self.line}: {self.rule} — {self.excerpt}"


@dataclass(frozen=True)
class Allowance:
    """One exact string this scan excuses, and why it is not a credential."""

    excerpt: str
    reason: str


RULES: tuple[Rule, ...] = (
    Rule(
        "private key",
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
        "a private key block is committed; rotate the key and remove the file",
    ),
    Rule(
        "aws access key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "an AWS access key id is committed; rotate it",
    ),
    Rule(
        "github token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "a GitHub token is committed; revoke it",
    ),
    Rule(
        "slack token",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
        "a Slack token is committed; revoke it",
    ),
    Rule(
        "signed token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "a signed token is committed; it is readable by anybody who can read the repository",
    ),
    Rule(
        "credential in a url",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
        "a connection string carries a password; move it to the environment",
    ),
)
"""Every shape this scan knows. A merge that adds one of these fails."""

MARKER = "not-a-credential"
"""The marker a line carries to say, in review, that its credential is invented."""

ALLOWED: tuple[Allowance, ...] = (
    Allowance(
        "postgresql://canon:hunter2@db.internal:5432/canon",
        "the fabricated connection string the outcome tests assert never reaches a "
        "caller; it is in revisions already made, where no marker can be added",
    ),
)
"""What is excused wherever it appears, each with the reason it is safe."""

PLACEHOLDER = re.compile(r"[{}$<>]")
"""An interpolation rather than a value: `https://oauth2:{TOKEN}@…` is a template."""


def allowed(excerpt: str, line: str) -> bool:
    """Whether this match is a fabrication rather than a credential."""
    if PLACEHOLDER.search(excerpt) or MARKER in line:
        return True
    return any(excerpt in allowance.excerpt for allowance in ALLOWED)


def findings_in(text: str, where: str, rules: Sequence[Rule] = RULES) -> tuple[Finding, ...]:
    """Every rule that fires in this text, with the line it fired on."""
    found: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for rule in rules:
            match = rule.pattern.search(line)
            if match is not None and not allowed(match.group(0), line):
                found.append(
                    Finding(where=where, line=number, rule=rule.name, excerpt=match.group(0))
                )
    return tuple(found)


def readable(content: bytes) -> str | None:
    """That content as text, or nothing when it is a blob rather than a file."""
    if NULL in content or len(content) > MAX_BYTES:
        return None
    return content.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# The repository: the working tree, and every revision behind it
# --------------------------------------------------------------------------


def git(root: Path, arguments: Sequence[str], capture: bool = True) -> str:
    """One git command in that repository."""
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=capture,
        text=True,
    )
    return completed.stdout


def working_files(root: Path) -> tuple[Path, ...]:
    """Every file git would carry: tracked, plus anything not ignored."""
    listed = git(root, ["ls-files", "--cached", "--others", "--exclude-standard"])
    return tuple(root / name for name in listed.splitlines() if (root / name).is_file())


def history_blobs(root: Path, revision: str = "HEAD") -> Iterator[tuple[str, bytes]]:
    """Every blob reachable from that revision, named by the path it was at.

    Read through `git cat-file --batch` in one pass rather than one process per
    object: a scan that took a second per commit is a scan that gets moved out
    of the merge gate within a month.
    """
    listed = git(root, ["rev-list", "--objects", revision]).splitlines()
    named = [line.split(" ", 1) for line in listed if " " in line]
    if not named:
        return
    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        for object_id, path in named:
            process.stdin.write(f"{object_id}\n".encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3 or header[1] != "blob":
                _skip(process.stdout, header)
                continue
            content = process.stdout.read(int(header[2]))
            process.stdout.read(1)
            yield f"{path}@{object_id[:8]}", content
    finally:
        process.stdin.close()
        process.wait(timeout=30)


def _skip(stream, header: Sequence[str]) -> None:
    """Consume a non-blob object's body so the stream stays aligned."""
    if len(header) == 3:
        stream.read(int(header[2]) + 1)


def scan_files(paths: Iterable[Path], root: Path) -> tuple[Finding, ...]:
    """Every finding in those files, named relative to the repository."""
    found: list[Finding] = []
    for path in paths:
        text = readable(path.read_bytes())
        if text is not None:
            found.extend(findings_in(text, str(path.relative_to(root))))
    return tuple(found)


def scan_history(root: Path, revision: str = "HEAD") -> tuple[Finding, ...]:
    """Every finding in every blob reachable from that revision."""
    found: list[Finding] = []
    for name, content in history_blobs(root, revision):
        text = readable(content)
        if text is not None:
            found.extend(findings_in(text, name))
    return tuple(found)


def scan_repository(root: Path, revision: str = "HEAD") -> tuple[Finding, ...]:
    """The merge gate: what is here now, and what any revision behind it carries."""
    return scan_files(working_files(root), root) + scan_history(root, revision)


# --------------------------------------------------------------------------
# The artifact: the files an image contains, against configured secret values
# --------------------------------------------------------------------------

COPY = re.compile(r"^COPY\s+(?:--[^\s]+\s+)*(?P<sources>.+?)\s+\S+\s*$", re.MULTILINE)
"""What a `Dockerfile` puts into the image. `--from=` stages copy no repository
content, so their sources are read the same way and simply do not exist here.
"""


def artifact_sources(dockerfile: str) -> tuple[str, ...]:
    """The repository paths this image is built out of, in the order copied."""
    sources: list[str] = []
    for match in COPY.finditer(dockerfile):
        sources.extend(
            source
            for source in match.group("sources").split()
            if not source.startswith("--") and source not in sources
        )
    return tuple(sources)


def artifact_files(root: Path, dockerfile: str) -> tuple[Path, ...]:
    """Every file those paths resolve to, which is what the image would contain."""
    found: list[Path] = []
    for source in artifact_sources(dockerfile):
        target = root / source
        if target.is_file():
            found.append(target)
        elif target.is_dir():
            found.extend(path for path in sorted(target.rglob("*")) if path.is_file())
    return tuple(found)


def values_found(paths: Iterable[Path], values: Sequence[str], root: Path) -> tuple[Finding, ...]:
    """Where any of those configured values appears in those files.

    The *values*, never the names: `CANON_DATABASE_URL` belongs in the image's
    documentation and in nothing else, and what may not be there is what it is
    set to in some environment.
    """
    wanted = [value for value in values if value.strip()]
    found: list[Finding] = []
    for path in paths:
        text = readable(path.read_bytes())
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            found.extend(
                Finding(
                    where=str(path.relative_to(root)),
                    line=number,
                    rule="configured secret",
                    excerpt="the value of a declared secret setting appears here",
                )
                for value in wanted
                if value in line
            )
    return tuple(found)


def scan_artifact(root: Path, dockerfile: Path, values: Sequence[str]) -> tuple[Finding, ...]:
    """An artifact's contents, against the values of the declared secret settings."""
    text = dockerfile.read_text(encoding="utf-8")
    files = artifact_files(root, text)
    return values_found(files, values, root) + scan_files(files, root)


__all__ = [
    "ALLOWED",
    "MARKER",
    "MAX_BYTES",
    "RULES",
    "Allowance",
    "Finding",
    "Rule",
    "allowed",
    "artifact_files",
    "artifact_sources",
    "findings_in",
    "history_blobs",
    "readable",
    "scan_artifact",
    "scan_files",
    "scan_history",
    "scan_repository",
    "values_found",
    "working_files",
]
