"""The in-memory `AnnotationWriter` — assets, their annotations, and a refusal.

It holds one dictionary of asset identifier to annotation list and nothing else,
which is the fake honouring the port's actual promise rather than a weaker one:
there is no path in it, so nothing it does could write beside a repository, and
:meth:`InMemoryAnnotationWriter.append` on an asset it does not hold raises
instead of creating one — because *"an automated caller SHALL only write against
an asset that already exists"* has to be true of every implementation or the
conformance suite is checking the adapter alone.

:meth:`refuse_with` and :meth:`fail_with` exist because the conflicted file and
the unreachable destination are specified behaviour (task 3.4), and a fake that
could only succeed would let the difference between them rot.
"""

from __future__ import annotations

from cybercanon.application.ports.annotation_writer import (
    AnnotationWriteRefused,
    AnnotationWriteUnavailable,
    WrittenAnnotation,
)
from cybercanon.domain.annotations import Annotation


class InMemoryAnnotationWriter:
    """One project's assets and their annotation lists, kept in a dictionary."""

    def __init__(self, committed: bool = False) -> None:
        self._paths: dict[str, str] = {}
        self._annotations: dict[str, list[Annotation]] = {}
        self._failure: Exception | None = None
        self.committed = committed
        self.appends = 0

    # -- seeding ---------------------------------------------------------

    def declare(self, asset_id: str, path: str = "", *annotations: Annotation) -> None:
        """This asset exists here, at this path, holding these annotations."""
        self._paths[asset_id] = path or f"assets/{asset_id}/asset.yaml"
        self._annotations[asset_id] = list(annotations)

    def refuse_with(self, reason: str = "the specification file is in conflict") -> None:
        """Make the next write refuse as a conflict, writing nothing."""
        self._failure = AnnotationWriteRefused("the specification", reason)

    def fail_with(self, error: Exception | None) -> None:
        """Make every operation raise. ``None`` clears it."""
        self._failure = error

    def recorded(self, asset_id: str) -> tuple[Annotation, ...]:
        """What this asset holds now — what a test asserts nothing was written to."""
        return tuple(self._annotations.get(asset_id, ()))

    # -- port ------------------------------------------------------------

    def locate(self, project: str, asset_id: str) -> str | None:
        self._raise_if_failing()
        return self._paths.get(asset_id)

    def annotations(self, project: str, asset_id: str) -> tuple[Annotation, ...]:
        self._raise_if_failing()
        if asset_id not in self._annotations:
            raise AnnotationWriteUnavailable(asset_id, "no such asset is declared here")
        return tuple(self._annotations[asset_id])

    def append(self, project: str, asset_id: str, annotation: Annotation) -> WrittenAnnotation:
        self._raise_if_failing()
        if asset_id not in self._annotations:
            raise AnnotationWriteUnavailable(asset_id, "no such asset is declared here")
        self._annotations[asset_id].append(annotation)
        self.appends += 1
        return WrittenAnnotation(
            path=self._paths[asset_id], annotation=annotation, committed=self.committed
        )

    def _raise_if_failing(self) -> None:
        if self._failure is not None:
            raise self._failure


__all__ = ["InMemoryAnnotationWriter"]
