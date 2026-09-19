"""Task 5.7 — what a read answers while the index is being rebuilt.

`deployment-operations`, on the degradation a recovery is allowed to cause:
*"an index rebuild is in progress ... reads that cannot be served from the
partial index SHALL report unavailability rather than an incomplete answer"*.
Beside it, the readiness rule: *"answers derivable from the working copy alone
SHALL continue to be served"*.

Those two sentences decide which endpoint does what, and the decision is
:class:`~cybercanon.application.use_cases.deployment_status.IndexRead`:

* a **listing or a search** is refused for as long as the rebuild runs, because
  its completeness *is* the answer and a caller cannot tell a short page from a
  finished one;
* a **lookup** is served when the row is there — it was written from the working
  copy and it is the same answer the finished index will give — and refused when
  it is not, because *"no such asset"* and *"not indexed yet"* are
  indistinguishable and mean opposite things;
* a **specification, a briefing or a validation** keeps answering, because none
  of them reads the index at all.

The surface is the real application over the in-memory fakes, so what is
asserted is the endpoint's answer rather than a function's return value.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from http_world import PROJECT, SCOUT, SCOUT_SPEC, a_surface

from cybercanon.application.use_cases.deployment_status import INDEX_REBUILDING

pytestmark = pytest.mark.unit

ASSETS = f"/v1/projects/{PROJECT}/assets"
LOOKUP = f"{ASSETS}/{SCOUT}/locations"
SEARCH = f"/v1/projects/{PROJECT}/search"
SPECIFICATION = f"{ASSETS}/{SCOUT}"
BRIEFING = f"{ASSETS}/{SCOUT}/briefing"

OTHER = "mule"


def rebuilding(wired) -> None:
    """Mark this project's index as being rebuilt, as a rebuild would."""
    wired.surface.journal.building(PROJECT)


# --------------------------------------------------------------------------
# The answers whose completeness is the answer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [ASSETS, SEARCH])
def test_a_listing_is_unavailable_rather_than_incomplete_during_a_rebuild(path: str) -> None:
    wired = a_surface()
    rebuilding(wired)

    response = wired.get(path, params={"q": SCOUT} if path == SEARCH else None)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["error"]["id"] == INDEX_REBUILDING


def test_the_refusal_says_the_index_is_being_rebuilt_and_names_the_project() -> None:
    wired = a_surface()
    rebuilding(wired)

    message = wired.get(ASSETS).json()["error"]["message"]

    assert PROJECT in message
    assert "rebuilt" in message


# --------------------------------------------------------------------------
# A lookup: a hit is a fact, a miss is not an answer
# --------------------------------------------------------------------------


def test_a_lookup_that_the_partial_index_can_answer_is_served() -> None:
    """The row was written from the working copy; a rebuild will not change it."""
    wired = a_surface()
    rebuilding(wired)

    response = wired.get(LOOKUP)

    assert response.status_code == HTTPStatus.OK


def test_a_lookup_the_partial_index_misses_reports_unavailability_not_absence() -> None:
    """*"Not indexed yet"* and *"no such asset"* are opposite answers."""
    wired = a_surface()
    rebuilding(wired)

    response = wired.get(f"{ASSETS}/{OTHER}/locations")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["error"]["id"] == INDEX_REBUILDING


def test_the_same_miss_is_an_ordinary_not_found_when_nothing_is_rebuilding() -> None:
    wired = a_surface()

    response = wired.get(f"{ASSETS}/{OTHER}/locations")

    assert response.status_code == HTTPStatus.NOT_FOUND


# --------------------------------------------------------------------------
# What the working copy alone can answer keeps answering
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [SPECIFICATION, BRIEFING])
def test_a_read_served_from_the_working_copy_is_unaffected(path: str) -> None:
    wired = a_surface()
    rebuilding(wired)

    assert wired.get(path).status_code == HTTPStatus.OK


def test_every_read_answers_again_once_the_rebuild_has_finished() -> None:
    wired = a_surface()
    rebuilding(wired)
    wired.surface.journal.built(PROJECT, "a-revision")

    assert wired.get(ASSETS).status_code == HTTPStatus.OK
    assert wired.get(SEARCH, params={"q": SCOUT}).status_code == HTTPStatus.OK
    assert wired.get(LOOKUP).status_code == HTTPStatus.OK


def test_another_projects_rebuild_does_not_refuse_this_ones_reads() -> None:
    """The journal is per project, and so is the degradation."""
    wired = a_surface(assets={SCOUT: SCOUT_SPEC})
    wired.surface.journal.building("some-other-game")

    assert wired.get(ASSETS).status_code == HTTPStatus.OK
