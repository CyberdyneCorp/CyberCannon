"""Tasks 7.1 and 7.6 — the runbook says what it must, and the gate bites.

Two halves, and they fail for different reasons.

**The committed page (7.1).** `deployment-operations` requires *"a documented
recovery procedure with a stated expected duration"* for each of the three
volumes, and *"no recovery procedure SHALL depend on a backup of the index or of
the blob store."* Both are properties of a file in the repository, so both are
checked here, on every build. The second one is checked by searching for the
words: a page that said "restore from the nightly dump" would be a page that had
quietly changed the architecture, and the only way that gets noticed is if
somebody is looking for those words.

**The gate over the drill log (7.6).** `review` fails when a procedure has never
been drilled, when its most recent drill is older than the stated interval, or
when that drill took longer than the page says it should. Each of those is
verified against a **fabricated** record rather than by waiting a week, because
a gate nobody has seen fail is a gate nobody knows works.

What is deliberately *not* here: the staleness check is not run against today's
date over the committed log. Staleness is a function of the calendar rather than
of the change under review, and a build that failed on a Tuesday for a
repository nobody had touched would teach people to ignore it. That gate is
`just drill-check`, run by the release pipeline and by the drill job itself; the
justfile says so where somebody looking for it will read it.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from canon_drill.records import (
    BLOB_RE_MIRROR,
    DRILL_LOG_HEADING,
    INDEX_REBUILD,
    INTERVAL,
    LEDGER_PATH,
    PROCEDURES,
    WORKING_COPY_RE_CLONE,
    Drill,
    LedgerMalformed,
    appended,
    drills,
    expectations,
    format_duration,
    latest,
    parse_duration,
    review,
)

RECOVERY_RECIPES = ("drill", "drill-check")

BACKUP_WORDS = ("pg_dump", "pg_restore", "restore from", "nightly dump", "snapshot restore")
"""Phrases that would mean the index had quietly become authoritative (D5)."""

TODAY = date(2026, 9, 22)


@pytest.fixture(scope="module")
def document(repo_root: Path) -> str:
    text = (repo_root / LEDGER_PATH).read_text(encoding="utf-8")
    assert text.strip(), f"{LEDGER_PATH} is the runbook a lost volume is recovered from"
    return text


# --------------------------------------------------------------------------
# 7.1 — three procedures, three stated durations, no backup anywhere
# --------------------------------------------------------------------------


def test_the_page_documents_all_three_procedures(document: str) -> None:
    """One per persistent volume: the copy, the index, the blob mirror."""
    named = {one.procedure for one in expectations(document)}

    assert named == set(PROCEDURES)


@pytest.mark.parametrize("procedure", PROCEDURES)
def test_each_procedure_has_a_section_of_its_own(document: str, procedure: str) -> None:
    """A row in a table is not a procedure somebody can follow at 3 a.m."""
    assert f"### `{procedure}`" in document


@pytest.mark.parametrize("procedure", PROCEDURES)
def test_each_procedure_states_an_expected_duration(document: str, procedure: str) -> None:
    stated = {one.procedure: one.expected for one in expectations(document)}

    assert stated[procedure] > timedelta(0), (
        f"{procedure} has no expected duration, so a drill has nothing to fail against"
    )


def test_no_procedure_references_a_backup_or_a_restore(document: str) -> None:
    """*"No recovery procedure SHALL depend on a backup of the index or of the
    blob store."* The page is allowed to say there is none; it is not allowed to
    tell somebody to use one."""
    lowered = document.lower()
    found = [word for word in BACKUP_WORDS if word in lowered]

    assert not found, (
        f"{LEDGER_PATH} points at {found}; the index and the blob mirror are "
        "derived, and a restore path is what makes a rebuild path rot"
    )


def test_the_page_states_that_there_is_no_backup_on_purpose(document: str) -> None:
    """Silence would leave the next operator looking for the dump that is not there."""
    assert "no backup of the index" in document
    assert "D5" in document


def test_each_procedure_names_the_volume_it_recovers(document: str) -> None:
    for volume in ("/data/worktrees", "postgres", "minio"):
        assert volume in document


def test_the_release_and_drill_commands_are_recipes(recipes: dict[str, object]) -> None:
    """*"There is exactly one way to run any operation, and it is a recipe."*"""
    missing = [name for name in RECOVERY_RECIPES if name not in recipes]

    assert not missing, f"{missing} are not recipes, so a drill would invoke a tool directly"


def test_the_page_names_the_commands_that_run_and_check_the_drills(document: str) -> None:
    for name in RECOVERY_RECIPES:
        assert f"just {name}" in document


def test_the_stated_interval_and_the_gate_agree(document: str) -> None:
    """A page saying one interval while the check used another would be worse than none."""
    assert f"every {INTERVAL.days} days" in document
    assert f"{INTERVAL.days}-day interval" in document


# --------------------------------------------------------------------------
# 7.1 — "Drills are executed, not assumed": a dated, measured record each
# --------------------------------------------------------------------------


@pytest.mark.parametrize("procedure", PROCEDURES)
def test_each_procedure_carries_its_most_recent_execution(document: str, procedure: str) -> None:
    """*"Each of the three procedures SHALL carry the date and measured duration
    of its most recent execution."*"""
    most_recent = latest(drills(document), procedure)

    assert most_recent is not None, f"{procedure} has never been drilled"
    assert most_recent.measured > timedelta(0)
    assert most_recent.on <= date.today()


def test_every_recorded_duration_is_within_its_expectation(document: str) -> None:
    """The half of the gate that *is* a function of the repository."""
    stated = {one.procedure: one.expected for one in expectations(document)}
    over = [
        one for one in drills(document) if one.measured > stated.get(one.procedure, timedelta.max)
    ]

    assert not over, (
        f"recorded drills exceeded their stated duration: {[one.row() for one in over]}"
    )


def test_the_log_is_machine_written_and_says_so(document: str) -> None:
    assert DRILL_LOG_HEADING in document
    assert "Nobody edits this table by hand" in document


# --------------------------------------------------------------------------
# 7.6 — the gate, against fabricated records
# --------------------------------------------------------------------------


def _fabricated(document: str, *recorded: Drill) -> str:
    """The committed page with its drill log replaced by these rows."""
    head, _, rest = document.partition(DRILL_LOG_HEADING)
    header = "\n".join(rest.splitlines()[:4])
    return f"{head}{DRILL_LOG_HEADING}\n{header}\n" + "\n".join(one.row() for one in recorded)


def _fresh(on: date = TODAY) -> tuple[Drill, ...]:
    return tuple(Drill(on=on, procedure=name, measured=timedelta(seconds=2)) for name in PROCEDURES)


def test_a_log_whose_drills_are_recent_and_quick_passes(document: str) -> None:
    """The control: without this, every case below could be passing by accident."""
    assert review(_fabricated(document, *_fresh()), today=TODAY) == ()


def test_a_drill_older_than_the_interval_fails(document: str) -> None:
    stale = TODAY - INTERVAL - timedelta(days=1)

    complaints = review(_fabricated(document, *_fresh(on=stale)), today=TODAY)

    assert {one.procedure for one in complaints} == set(PROCEDURES)
    assert all("stated interval" in one.reason for one in complaints)


def test_only_the_overdue_procedure_is_named(document: str) -> None:
    """A gate that failed all three because one was overdue would be unreadable."""
    stale = TODAY - INTERVAL - timedelta(days=1)
    log = _fabricated(
        document,
        Drill(on=stale, procedure=INDEX_REBUILD, measured=timedelta(seconds=2)),
        Drill(on=TODAY, procedure=BLOB_RE_MIRROR, measured=timedelta(seconds=2)),
        Drill(on=TODAY, procedure=WORKING_COPY_RE_CLONE, measured=timedelta(seconds=2)),
    )

    complaints = review(log, today=TODAY)

    assert [one.procedure for one in complaints] == [INDEX_REBUILD]


def test_a_drill_that_exceeded_the_stated_expectation_fails(document: str) -> None:
    """*"A drill whose duration exceeds the stated expectation fails."*"""
    stated = {one.procedure: one.expected for one in expectations(document)}
    over = stated[INDEX_REBUILD] + timedelta(minutes=1)
    log = _fabricated(
        document,
        Drill(on=TODAY, procedure=INDEX_REBUILD, measured=over),
        Drill(on=TODAY, procedure=BLOB_RE_MIRROR, measured=timedelta(seconds=2)),
        Drill(on=TODAY, procedure=WORKING_COPY_RE_CLONE, measured=timedelta(seconds=2)),
    )

    complaints = review(log, today=TODAY)

    assert [one.procedure for one in complaints] == [INDEX_REBUILD]
    assert "over the stated" in complaints[0].reason
    assert format_duration(over) in complaints[0].reason


def test_a_procedure_that_was_never_drilled_fails(document: str) -> None:
    log = _fabricated(
        document,
        Drill(on=TODAY, procedure=BLOB_RE_MIRROR, measured=timedelta(seconds=2)),
        Drill(on=TODAY, procedure=WORKING_COPY_RE_CLONE, measured=timedelta(seconds=2)),
    )

    complaints = review(log, today=TODAY)

    assert [one.procedure for one in complaints] == [INDEX_REBUILD]
    assert "never been drilled" in complaints[0].reason


def test_one_drill_can_be_both_overdue_and_too_slow(document: str) -> None:
    """Two complaints about one procedure, because they are two different problems."""
    stated = {one.procedure: one.expected for one in expectations(document)}
    log = _fabricated(
        document,
        Drill(
            on=TODAY - INTERVAL - timedelta(days=1),
            procedure=INDEX_REBUILD,
            measured=stated[INDEX_REBUILD] + timedelta(minutes=1),
        ),
        Drill(on=TODAY, procedure=BLOB_RE_MIRROR, measured=timedelta(seconds=2)),
        Drill(on=TODAY, procedure=WORKING_COPY_RE_CLONE, measured=timedelta(seconds=2)),
    )

    complaints = review(log, today=TODAY)

    assert len(complaints) == 2
    assert {one.procedure for one in complaints} == {INDEX_REBUILD}


def test_a_page_with_no_drill_log_is_refused_rather_than_passed(document: str) -> None:
    """A gate that treated a missing table as "nothing to complain about" would
    be the failure it exists to catch, reported as fine."""
    with pytest.raises(LedgerMalformed):
        review(document[: document.index(DRILL_LOG_HEADING)], today=TODAY)


# --------------------------------------------------------------------------
# The ledger's own plumbing, because the gate is only as good as its parser
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("0.25s", timedelta(seconds=0.25)),
        ("90s", timedelta(seconds=90)),
        ("12m", timedelta(minutes=12)),
        ("3m12s", timedelta(minutes=3, seconds=12)),
        ("1h30m", timedelta(hours=1, minutes=30)),
    ],
)
def test_durations_round_trip(written: str, expected: timedelta) -> None:
    assert parse_duration(written) == expected
    assert parse_duration(format_duration(expected)) == pytest.approx(
        expected, abs=timedelta(seconds=1)
    )


@pytest.mark.parametrize("written", ["", "soon", "12", "1 minute", "m"])
def test_a_duration_the_gate_cannot_read_is_refused(written: str) -> None:
    with pytest.raises(LedgerMalformed):
        parse_duration(written)


def test_appending_adds_rows_and_changes_nothing_else(document: str) -> None:
    added = Drill(on=TODAY, procedure=INDEX_REBUILD, measured=timedelta(seconds=3))

    after = appended(document, [added])

    assert drills(after) == (*drills(document), added)
    assert expectations(after) == expectations(document)
    assert after.startswith(document[: document.index(DRILL_LOG_HEADING)])


def test_the_committed_log_rows_are_all_well_formed(document: str) -> None:
    """Every row parses, so the gate never passes by failing to read one."""
    rows = re.findall(r"^\| \d{4}-\d{2}-\d{2} \|.*\|$", document, flags=re.MULTILINE)

    assert len(rows) == len(drills(document)) >= len(PROCEDURES)
