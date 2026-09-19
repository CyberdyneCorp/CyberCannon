"""Rendering: use-case values as JSON, and not one decision among them.

Every function here takes something a use case produced and returns a mapping.
There is no branch on specification content in this module and there cannot be
one — `tests/tooling/test_http_adapter_is_a_translator.py` walks the syntax tree
of this package looking for exactly that — so a field that is absent renders as
absent, and a field whose value would have to be *decided* is not rendered at
all. A default triangle budget invented here would be the web surface quietly
disagreeing with `canon validate`, which is the failure this product exists to
prevent.

The field names deliberately match the command line's structured output
(:mod:`cybercanon.adapters.inbound.cli.payload`), because `http-api` requires
the same validation to agree across surfaces and the cheapest way to check that
is to compare the two documents. They are **not shared code**: a cross-adapter
import would make one surface's rendering a dependency of the other's, and the
agreement that matters is agreement about the *verdict*, which is shared already
— it is the same use case.
"""

from __future__ import annotations

from typing import Any

from cybercanon.application.use_cases.compile_spec import CompiledBriefing, CompiledSpec
from cybercanon.application.use_cases.hosted_repository import WriteOutcome
from cybercanon.application.use_cases.lookup_assets import (
    AssetRow,
    Location,
    LocationAnswer,
    OwnerPresentation,
    SearchAnswer,
)
from cybercanon.application.use_cases.spec_lens import LensedSpec
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.report import NotEvaluated, Report
from cybercanon.domain.violations import SpecViolation, Violation


def asset_row(row: AssetRow) -> dict[str, Any]:
    """One line of a listing, addressed by the identifier the specification uses."""
    return {
        "asset": row.asset_id,
        "name": row.name,
        "status": row.status,
        "owners": [owner(entry) for entry in row.owners],
    }


def owner(presentation: OwnerPresentation) -> dict[str, Any]:
    return {
        "discipline": presentation.discipline,
        "display": presentation.display,
        "recorded": presentation.is_recorded,
        "unmapped": presentation.is_unmapped,
    }


def location(entry: Location) -> dict[str, Any]:
    return {"label": entry.label, "value": entry.text, "recorded": entry.is_recorded}


def lookup(answer: LocationAnswer) -> dict[str, Any]:
    """Every recorded location of one asset, with the unrecorded ones still named.

    Unrecorded entries travel rather than being filtered out, because *"where is
    the export"* answered by silence is indistinguishable from the question not
    having been asked.
    """
    return {
        "asset": answer.asset_id,
        "name": answer.name,
        "status": answer.status,
        "project": answer.project,
        "locations": [location(entry) for entry in answer.locations],
        "owners": [owner(entry) for entry in answer.owners],
        "stale": answer.stale,
        "notice": answer.notice,
    }


def search(answer: SearchAnswer) -> dict[str, Any]:
    """What a term matched, in the cascade's order — which is the ranking (D9)."""
    return {
        "term": answer.term,
        "project": answer.project,
        "assets": list(answer.asset_ids),
        "recorded_as_miss": answer.recorded_as_miss,
    }


def lensed(spec: LensedSpec) -> dict[str, Any]:
    """One compiled specification as a discipline sees it.

    `full` travels beside `body` for the reason the use case states: a reader
    that took a projection for the whole truth would model against a subset.
    """
    return {
        "asset": spec.asset_id,
        "source": spec.source,
        "lens": str(spec.lens) if spec.lens else None,
        "body": spec.body,
        "full": spec.full,
        "notice": spec.notice,
    }


def compiled(spec: CompiledSpec) -> dict[str, Any]:
    """An asset's compiled briefing — the same text the command line writes."""
    return {"asset": spec.asset_id, "source": spec.source, "text": spec.text}


def project_briefing(briefing: CompiledBriefing) -> dict[str, Any]:
    """The project's standing rules, with no asset in them."""
    return {"project": briefing.project, "text": briefing.text}


def validation(outcome: ValidationOutcome) -> dict[str, Any]:
    """One export against its governing specification, as data.

    The verdict, its violations and the rules that could not be evaluated are
    three distinct fields, exactly as they are on the command line: folding the
    third into the second would tell a client a rule failed when it never ran.
    """
    return {
        "spec": outcome.spec_path,
        "passed": outcome.passed,
        **report(outcome.report),
        "spec_warnings": [spec_violation(warning) for warning in outcome.spec_warnings],
    }


def report(value: Report) -> dict[str, Any]:
    return {
        "asset": value.asset_id,
        "export": value.export,
        "export_format": str(value.export_format),
        "outcome": value.outcome,
        "violations": [violation(entry) for entry in value.violations],
        "not_evaluated": [not_evaluated(entry) for entry in value.not_evaluated],
        "passed_rules": list(value.passed_rules),
    }


def violation(entry: Violation) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "severity": str(entry.severity),
        "subject": entry.subject,
        "observed": entry.observed,
        "expected": entry.expected,
        "message": entry.message,
    }


def spec_violation(entry: SpecViolation) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "severity": str(entry.severity),
        "subject": entry.subject,
        "observed": entry.observed,
        "expected": entry.expected,
        "message": entry.message,
    }


def written(outcome: WriteOutcome) -> dict[str, Any]:
    """One applied edit: the commit it became, and where it landed.

    The revision is the one the push produced, so a caller composing its next
    edit has the value it must declare — which is what keeps the revision
    precondition a round trip rather than a guess.
    """
    return {
        "project": outcome.project,
        "revision": outcome.revision.value,
        "paths": list(outcome.paths),
        "author": outcome.commit.author.email,
        "message": outcome.commit.message,
        "attempts": outcome.attempts,
    }


def not_evaluated(entry: NotEvaluated) -> dict[str, Any]:
    return {
        "rule_id": entry.rule_id,
        "missing_fact": entry.missing_fact.label,
        "reason": entry.reason,
    }


__all__ = [
    "asset_row",
    "compiled",
    "lensed",
    "location",
    "lookup",
    "not_evaluated",
    "owner",
    "project_briefing",
    "report",
    "search",
    "spec_violation",
    "validation",
    "violation",
    "written",
]
