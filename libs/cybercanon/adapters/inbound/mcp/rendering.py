"""Prose for a context window — the whole of what the MCP adapter decides (D1).

A tool response is read by a language model and, one day, by the person holding
the terminal it was printed into. So the shapes the application returns are
turned into two things and nothing else:

* **compact tables for listings** — one row per asset, the columns a reader
  chooses between, and no record dumped in full. A listing that returned every
  field of every asset would spend a context window proving it had one;
* **markdown for specifications** — the compiled briefing exactly as it stands,
  because it is already the document a person reads, and re-rendering it here
  would be the second compiler D2 exists to prevent.

Two rules this module keeps, and both are about not becoming the place where the
product acquires a second opinion:

* **Nothing here decides anything.** No threshold, no severity, no verdict and
  no rule appears below; every value was settled by the domain and by the use
  case before this module was called. `tests/tooling/test_mcp_adapter_is_a_formatter.py`
  asserts it structurally — there is no conditional in this package that reads
  specification content.
* **A projection says it is one.** A lensed read and an open-threads read carry
  a notice written by the use case, and it is emitted verbatim: an agent that
  took a subset for the whole contract would model against it, which is the one
  misreading worth spending two lines on.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from cybercanon.application.results import Refusal
from cybercanon.application.use_cases.diff_spec import SpecDifference
from cybercanon.application.use_cases.index_assets import UnreadableSpec
from cybercanon.application.use_cases.lookup_assets import (
    DISCIPLINES,
    AssetListing,
    AssetRow,
    LocationAnswer,
    SearchAnswer,
)
from cybercanon.application.use_cases.spec_lens import LensedSpec
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.report import NotEvaluated, Report
from cybercanon.domain.violations import Violation

NO_RESULTS = "nothing matched"
NO_ASSETS = "no asset is indexed for this project"
NOTHING_TO_REPORT = "nothing to report"
NEAREST = "closest matching identifiers"
UNREADABLE_HEADING = "Specifications that could not be read"
PASSING = "PASSING"
FAILING = "FAILING"
VERDICT = {True: PASSING, False: FAILING}

LOCATION_COLUMNS = ("location", "value")
ASSET_COLUMNS = ("asset", "name", "status", "art owner", "design owner", "code owner")
SEARCH_COLUMNS = ("asset", "name", "matched on", "status")
VIOLATION_COLUMNS = ("severity", "rule", "subject", "observed", "expected")


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------


def render_location(answer: LocationAnswer) -> str:
    """Where one asset's artifacts live — recorded and, explicitly, not recorded."""
    return _document(
        (
            _heading(answer.asset_id, answer.name),
            _note(answer.notice),
            _fields((("Status", answer.status), ("Project", answer.project))),
            _table(LOCATION_COLUMNS, ((place.label, place.text) for place in answer.locations)),
            _table(("owner", "person"), ((who.discipline, who.display) for who in answer.owners)),
        )
    )


def render_listing(listing: AssetListing, unreadable: Sequence[UnreadableSpec] = ()) -> str:
    """A project's assets as one compact table, with unreadable files beside it.

    The malformed specification is reported *next to* the listing rather than
    inside it or instead of it: an agent asking what exists still learns what
    exists, and separately learns which file somebody has to fix.
    """
    return _document(
        (
            f"## Assets — {len(listing)} in project {listing.project or '(unnamed)'}",
            _note(_filters(listing)),
            _table(ASSET_COLUMNS, (_asset_row(row) for row in listing.rows), empty=NO_ASSETS),
            _unreadable(unreadable),
        )
    )


def render_search(answer: SearchAnswer, nearest: Sequence[str] = ()) -> str:
    """The ranked cascade as a compact table, or what to try instead."""
    return _document(
        (
            f"## Search `{answer.term}` — {len(answer)} result(s)",
            _table(
                SEARCH_COLUMNS,
                (
                    (hit.asset_id, hit.entry.name, hit.kind.value, hit.entry.status or "")
                    for hit in answer.hits
                ),
                empty=f"{NO_RESULTS} for `{answer.term}`",
            ),
            _nearest(nearest),
        )
    )


def render_nearest(asset_id: str, nearest: Sequence[str]) -> str:
    """What a caller that named an unknown asset is offered instead."""
    return _document((f"## `{asset_id}` is not indexed", _nearest(nearest)))


# --------------------------------------------------------------------------
# Specifications
# --------------------------------------------------------------------------


def render_spec(lensed: LensedSpec) -> str:
    """The briefing itself — markdown a person would read, notice included.

    `LensedSpec.text` already carries the use case's own notice in front of the
    projection, so this hands it on unchanged: the sentence that says which lens
    produced a response, and that a full specification exists, is written once
    in the application layer and cannot drift between surfaces.
    """
    return lensed.text


def render_difference(difference: SpecDifference) -> str:
    """How a specification moved since a revision, as semantic statements (D10)."""
    return _document(
        (
            _heading(difference.asset_id, f"since {difference.revision}"),
            difference.summary,
            _bullets(difference.statements),
        )
    )


# --------------------------------------------------------------------------
# Validation — the same use case the command line calls
# --------------------------------------------------------------------------


def render_validation(outcome: ValidationOutcome) -> str:
    """One export's verdict, with every violation and everything not evaluated.

    Nothing is summarised away. A suppressed rule is named rather than counted,
    for the same reason the command line names it: a count is how a validator
    starts lying about its coverage.
    """
    report = outcome.report
    return _document(
        (
            f"## Validation — {report.export or '(export)'}",
            _fields(
                (
                    ("Asset", report.asset_id),
                    ("Specification", outcome.spec_path),
                    ("Format", str(report.export_format)),
                    ("Verdict", _verdict(outcome.passed)),
                )
            ),
            _table(
                VIOLATION_COLUMNS,
                (_violation_row(entry) for entry in report.violations),
                empty="no violations",
            ),
            _not_evaluated(report),
            f"{len(report.passed_rules)} rules passed",
        )
    )


# --------------------------------------------------------------------------
# Failure
# --------------------------------------------------------------------------


def render_failure(refusal: Refusal, nearest: Sequence[str] = ()) -> str:
    """Why a tool could not answer, and what would resolve it.

    Never an empty success and never the end of the session: a recoverable
    failure is an ordinary response whose content happens to be an explanation.
    """
    return _document((f"**Could not answer:** {refusal.message}", _nearest(nearest)))


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------


def _document(blocks: Iterable[str]) -> str:
    return "\n\n".join(block for block in blocks if block)


def _heading(identifier: str, title: str) -> str:
    return f"## {identifier} — {title}"


def _note(text: str) -> str:
    return f"> {text}" if text else ""


def _fields(fields: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f"- **{label}:** {value}" for label, value in fields if value)


def _bullets(lines: Iterable[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _table(columns: Sequence[str], rows: Iterable[Sequence[str]], empty: str = "") -> str:
    body = [f"| {' | '.join(str(cell) for cell in row)} |" for row in rows]
    if not body:
        return f"_{empty}_" if empty else ""
    header = (f"| {' | '.join(columns)} |", f"|{'---|' * len(columns)}")
    return "\n".join((*header, *body))


def _asset_row(row: AssetRow) -> tuple[str, ...]:
    return (row.asset_id, row.name, row.status, *(row.owner(who).display for who in DISCIPLINES))


def _filters(listing: AssetListing) -> str:
    applied = (("status", listing.status), ("owner", listing.owner), ("tag", listing.tag))
    named = ", ".join(f"{label} {value}" for label, value in applied if value)
    return f"filtered by {named}" if named else ""


def _nearest(nearest: Sequence[str]) -> str:
    if not nearest:
        return ""
    return f"{NEAREST}: " + ", ".join(f"`{identifier}`" for identifier in nearest)


def _unreadable(unreadable: Sequence[UnreadableSpec]) -> str:
    if not unreadable:
        return ""
    heading = f"### {UNREADABLE_HEADING} ({len(unreadable)})"
    return "\n".join((heading, "", _bullets(str(entry) for entry in unreadable)))


def _violation_row(violation: Violation) -> tuple[str, ...]:
    return (
        str(violation.severity),
        violation.rule_id,
        violation.subject,
        _value(violation.observed),
        _value(violation.expected),
    )


def _not_evaluated(report: Report) -> str:
    if not report.not_evaluated:
        return ""
    return "\n".join(
        (
            f"### Not evaluated ({len(report.not_evaluated)})",
            "",
            _bullets(_suppressed(entry) for entry in report.not_evaluated),
        )
    )


def _suppressed(entry: NotEvaluated) -> str:
    return f"{entry.rule_id} — needs {entry.missing_fact.label} — {entry.reason}"


def _verdict(passed: bool) -> str:
    """The verdict as a word — a lookup, never a branch: the domain already decided."""
    return VERDICT[passed]


def _value(value: str | None) -> str:
    return "—" if value is None else value


__all__ = [
    "ASSET_COLUMNS",
    "FAILING",
    "LOCATION_COLUMNS",
    "NEAREST",
    "NO_ASSETS",
    "NO_RESULTS",
    "PASSING",
    "SEARCH_COLUMNS",
    "UNREADABLE_HEADING",
    "VIOLATION_COLUMNS",
    "render_difference",
    "render_failure",
    "render_listing",
    "render_location",
    "render_nearest",
    "render_search",
    "render_spec",
    "render_validation",
]
