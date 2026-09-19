"""What every `Dismissals` SHALL do, whoever implements it (task 10.5).

Every clause is a sentence of `asset-requests` or of D9 rather than a property
of a dictionary or of a table:

* an item nobody dismissed is **not** dismissed — the default is unread, so a
  store that answered "everything" on an unknown person would hide every
  notification the system has;
* **dismissal is per person**: *"one of them dismisses it ... it SHALL remain
  unread for the other"*, which is only true if the recipient is part of the key;
* **dismissal is per project and per subject**, so one request being looked at
  says nothing about the next one;
* dismissing twice is the same fact, not an error — a double-click is not a
  failure mode.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cybercanon.application.ports.dismissals import Dismissal, Dismissals
from cybercanon.domain.identity import ActorId

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "cyberdyne-art"

RAFA = ActorId("auth|rafa")
ANA = ActorId("auth|ana")

REQUEST = "req-0001"
OTHER_REQUEST = "req-0002"

NOON = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def a_dismissal(
    actor: ActorId = RAFA,
    subject: str = REQUEST,
    project: str = PROJECT,
    at: datetime = NOON,
) -> Dismissal:
    return Dismissal(project=project, actor=actor, subject=subject, at=at)


class DismissalsContract:
    """The behaviour every dismissal store shares."""

    def test_nothing_is_dismissed_until_somebody_dismisses_it(
        self, implementation: Dismissals
    ) -> None:
        assert implementation.dismissed_by(RAFA, PROJECT) == frozenset()

    def test_a_dismissed_subject_reads_back(self, implementation: Dismissals) -> None:
        implementation.dismiss(a_dismissal())

        assert implementation.dismissed_by(RAFA, PROJECT) == frozenset({REQUEST})

    def test_one_persons_dismissal_leaves_it_unread_for_the_other(
        self, implementation: Dismissals
    ) -> None:
        """`asset-requests`: *"it SHALL remain unread for the other"*."""
        implementation.dismiss(a_dismissal(actor=RAFA))

        assert implementation.dismissed_by(ANA, PROJECT) == frozenset()

    def test_dismissal_is_per_subject(self, implementation: Dismissals) -> None:
        implementation.dismiss(a_dismissal(subject=REQUEST))

        assert OTHER_REQUEST not in implementation.dismissed_by(RAFA, PROJECT)

    def test_dismissal_is_per_project(self, implementation: Dismissals) -> None:
        implementation.dismiss(a_dismissal(project=PROJECT))

        assert implementation.dismissed_by(RAFA, OTHER_PROJECT) == frozenset()

    def test_dismissing_twice_is_the_same_fact(self, implementation: Dismissals) -> None:
        implementation.dismiss(a_dismissal())
        implementation.dismiss(a_dismissal(at=NOON.replace(hour=18)))

        assert implementation.dismissed_by(RAFA, PROJECT) == frozenset({REQUEST})

    def test_several_subjects_accumulate(self, implementation: Dismissals) -> None:
        implementation.dismiss(a_dismissal(subject=REQUEST))
        implementation.dismiss(a_dismissal(subject=OTHER_REQUEST))

        assert implementation.dismissed_by(RAFA, PROJECT) == frozenset({REQUEST, OTHER_REQUEST})
