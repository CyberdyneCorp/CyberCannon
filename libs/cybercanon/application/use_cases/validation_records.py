"""The validation outcome as a file in the repository — reading it (G2).

G2 makes a validation outcome repository content: *"written as a file beside the
asset and committed by the worker"*. This module is the half that knows what
that file is called, what is in it, and how to read one back; the half that
produces and commits one is
:mod:`cybercanon.application.use_cases.validation_worker`.

They are separate modules for a reason that is structural rather than tidy:
:func:`~cybercanon.application.use_cases.hosted_repository.rebuild_project_index`
has to read these files — a rebuild that did not would be a rebuild that lost
the answer, which is the guarantee this whole change exists to keep — and the
writer imports `hosted_repository` for `write_back`. Reader and writer in one
module would be an import cycle, and an index rebuild that silently dropped the
validated export would be the bug nobody notices until `where_is` goes quiet
again.

**The document is JSON, beside a YAML specification, for the same reason a
request's is** (`requests`, D7): it is machine-written, nobody diffs it for
design intent, it renders deterministically with sorted keys, and it keeps the
YAML reader — which is an adapter's — out of the application. `asset.yaml` is
untouched, because that is the file a contractor reads.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.domain.revisions import ContentHash, Revision
from cybercanon.domain.validation_outcome import AUTOMATION, ValidationRecord

RECORD_NAME = "asset.validation.json"
"""The file an outcome lives in, beside the `asset.yaml` that governs it.

Named after the specification it sits next to rather than after the export,
because `where_is` asks *which export was validated* — one answer per asset,
which is exactly one file per asset and no directory to enumerate.
"""

DOCUMENT_VERSION = 1
"""Bumped only by a change the previous reader cannot read."""


class ValidationUnreadable(OperationFailed):
    """The recorded outcome will not parse — a file somebody hand-edited."""

    kind = FailureKind.INVALID
    identifier = "validation.unreadable"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path} could not be read as a validation outcome: {reason}", path)
        self.reason = reason


def path_for(spec_path: str) -> str:
    """Where the outcome for the asset declared by that specification lives."""
    return PurePosixPath(spec_path).with_name(RECORD_NAME).as_posix()


def to_document(record: ValidationRecord) -> bytes:
    """One outcome as the bytes committed to its file.

    Deterministic by construction — sorted keys, fixed indent, trailing newline
    — because a renderer that reordered fields would produce a diff on every run
    and make the history unreadable for the one thing it is good for.
    """
    document = {
        "schema_version": DOCUMENT_VERSION,
        "asset": record.asset_id,
        "export": record.export,
        "export_hash": record.export_hash,
        "spec_hash": record.spec_hash,
        "passed": record.passed,
        "validated_at": record.validated_at.isoformat(),
        "attributed_to": record.attributed_to,
        "performed_by": record.performed_by,
        "errors": record.errors,
        "warnings": record.warnings,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def from_document(content: bytes, path: str = "") -> ValidationRecord:
    """The outcome those bytes hold, or a named failure.

    The round trip is the whole of the index-rebuild guarantee for a validated
    export: a field that does not survive `to_document` then `from_document` is
    an answer a rebuild would lose.
    """
    try:
        return _parsed(json.loads(content.decode("utf-8")))
    except (ValueError, KeyError, TypeError) as failure:
        raise ValidationUnreadable(path, str(failure) or type(failure).__name__) from failure


def _parsed(document: dict[str, object]) -> ValidationRecord:
    return ValidationRecord(
        asset_id=str(document["asset"]),
        export=str(document["export"]),
        export_hash=str(document["export_hash"]),
        passed=bool(document["passed"]),
        validated_at=datetime.fromisoformat(str(document["validated_at"])),
        spec_hash=str(document.get("spec_hash") or ""),
        attributed_to=str(document.get("attributed_to") or AUTOMATION),
        performed_by=str(document.get("performed_by") or ""),
        errors=int(document.get("errors") or 0),  # type: ignore[arg-type]
        warnings=int(document.get("warnings") or 0),  # type: ignore[arg-type]
    )


def recorded_validation(
    project: str,
    spec_path: str,
    *,
    repository_host: RepositoryHost,
    revision: Revision,
) -> ValidationRecord | None:
    """The outcome recorded beside that specification, or ``None``.

    ``None`` covers both *nobody has validated this asset* and *the file will
    not parse*, and the second is deliberate rather than lazy: the caller is a
    rebuild or a worker deciding whether to run, and neither is improved by
    refusing the whole pass over one hand-edited file. A file that will not
    parse is rewritten by the next run that produces an outcome, which is the
    repair, and :func:`from_document` is public so a surface that wants to
    report it can.
    """
    content = repository_host.read(project, path_for(spec_path), revision)
    if content is None:
        return None
    try:
        return from_document(content, path_for(spec_path))
    except ValidationUnreadable:
        return None


def digest_at(
    project: str,
    path: str,
    *,
    repository_host: RepositoryHost,
    revision: Revision,
) -> ContentHash | None:
    """What that file hashes to at that revision, or ``None`` when it is absent.

    The precondition an edit to it is composed against (D5), and the comparison
    :func:`~cybercanon.domain.validation_outcome.needs_validation` makes — one
    function, so the digest a run decided on and the digest its commit is
    conditioned on can never be taken differently.
    """
    content = repository_host.read(project, path, revision)
    return ContentHash.of(content) if content is not None else None


type ValidationLookup = Callable[[str], ValidationRecord | None]
"""How a caller answers *what outcome is recorded beside this specification*.

Injected the way :data:`~cybercanon.application.use_cases.index_assets.Fingerprinter`
is, and for the same reason: the index rebuild must be able to read these files
when it runs over a hosted working copy, and must not require a repository host
when it runs over a directory on a laptop.
"""


def no_validations(spec_path: str) -> ValidationRecord | None:
    """The default: this caller has no repository to read outcomes from."""
    return None


def validations_from(
    project: str,
    repository_host: RepositoryHost,
    revision: Revision,
) -> ValidationLookup:
    """A lookup that reads outcomes from one project at one revision (D3)."""

    def lookup(spec_path: str) -> ValidationRecord | None:
        return recorded_validation(
            project, spec_path, repository_host=repository_host, revision=revision
        )

    return lookup


__all__ = [
    "DOCUMENT_VERSION",
    "RECORD_NAME",
    "ValidationLookup",
    "ValidationUnreadable",
    "digest_at",
    "from_document",
    "no_validations",
    "path_for",
    "recorded_validation",
    "to_document",
    "validations_from",
]
