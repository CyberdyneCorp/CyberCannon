"""What every `AnnotationWriter` SHALL do, whoever implements it (task 2.2).

The contract is short because the port is, and every clause of it is a
requirement rather than a convenience:

* **an unknown asset is ``None``, never a creation.** `mcp-write-surface` is
  unambiguous — an automated caller *"SHALL NOT create an asset, create a
  specification file, or cause one to come into existence as a side effect of a
  write"* — so `locate` answers and `append` refuses, and neither brings an
  asset into being;
* **appending adds one entry and leaves the rest alone.** What was already
  recorded is still recorded, in the order it was recorded in, because the
  annotation list is what a person reads a thread from;
* **a write says whether it is durable.** The local writer answers `committed =
  False` and carries the sentence about the working copy (D2); a hosted one
  answers `True`. Both are honest, and the caller is told which;
* **the port names no path.** `append` names an asset, so nothing above this
  boundary can aim a write at a file of its choosing — the same structural
  refusal the `CredentialStore` contract makes about a credential.

It runs against the in-memory fake today and against `GitAnnotationWriter` the
moment task 3.3 lands, which is the point of writing it now: *"the fakes pass
the same conformance suite the real adapters will."*
"""

from __future__ import annotations

import pytest

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.annotation_writer import (
    UNCOMMITTED,
    AnnotationWriter,
)
from cybercanon.domain.annotations import AnnotationKind, ObservationKind
from cybercanon.domain.identity import AgentId
from cybercanon.domain.observations import observation, target_for

ASSET = "mech_scout"
ABSENT = "mech_scowt"
BLENDER = AgentId("blender-agent")


def an_observation(identifier: str = "obs_1", text: str = "12k is unreachable"):
    """One agent-authored observation, built through the domain's own constructor."""
    return observation(
        identifier=identifier,
        author="rafa",
        via=BLENDER,
        kind=AnnotationKind.TECHNICAL,
        observation_kind=ObservationKind.UNATTAINABLE_CONSTRAINT,
        text=text,
        target=target_for("head"),
        created_at="2026-03-01T12:00:00+00:00",
    )


class AnnotationWriterContract:
    """The behaviour every annotation writer shares."""

    def test_a_declared_asset_is_locatable(self, implementation: AnnotationWriter) -> None:
        assert implementation.locate("ronin", ASSET)

    def test_an_unknown_asset_locates_to_nothing(self, implementation: AnnotationWriter) -> None:
        """``None`` is an answer; the refusal that names it belongs to a use case."""
        assert implementation.locate("ronin", ABSENT) is None

    def test_an_asset_with_no_annotations_answers_with_none_of_them(
        self, implementation: AnnotationWriter
    ) -> None:
        assert implementation.annotations("ronin", ASSET) == ()

    def test_what_is_appended_comes_back(self, implementation: AnnotationWriter) -> None:
        written = implementation.append("ronin", ASSET, an_observation())

        assert written.id == "obs_1"
        assert implementation.annotations("ronin", ASSET) == (written.annotation,)

    def test_appending_adds_rather_than_replaces(self, implementation: AnnotationWriter) -> None:
        """A thread list is read in order; a write that reordered it would be a diff."""
        implementation.append("ronin", ASSET, an_observation("obs_1", "the first finding"))
        implementation.append("ronin", ASSET, an_observation("obs_2", "the second finding"))

        assert [entry.id for entry in implementation.annotations("ronin", ASSET)] == [
            "obs_1",
            "obs_2",
        ]

    def test_a_write_says_where_it_landed(self, implementation: AnnotationWriter) -> None:
        written = implementation.append("ronin", ASSET, an_observation())

        assert written.path
        assert written.path.endswith(".yaml")

    def test_an_uncommitted_write_says_so(self, implementation: AnnotationWriter) -> None:
        """D2: the response names the modified file and says it is uncommitted."""
        written = implementation.append("ronin", ASSET, an_observation())

        assert written.note == ("" if written.committed else UNCOMMITTED)

    def test_writing_to_an_unknown_asset_creates_nothing(
        self, implementation: AnnotationWriter
    ) -> None:
        """The requirement in one assertion: it refuses, and no asset appears."""
        with pytest.raises(OperationFailed):
            implementation.append("ronin", ABSENT, an_observation())

        assert implementation.locate("ronin", ABSENT) is None

    def test_reading_an_unknown_asset_is_a_failure_rather_than_an_empty_list(
        self, implementation: AnnotationWriter
    ) -> None:
        """ "No such asset" and "an asset with no annotations" are different answers."""
        with pytest.raises(OperationFailed):
            implementation.annotations("ronin", ABSENT)

    def test_the_port_offers_no_path_to_write_to(self, implementation: AnnotationWriter) -> None:
        """A write names an asset; nothing above this boundary chooses a file."""
        for name in ("locate", "annotations", "append"):
            annotations = getattr(getattr(implementation, name), "__annotations__", {})
            assert not any("Path" in str(kind) for kind in annotations.values()), name
