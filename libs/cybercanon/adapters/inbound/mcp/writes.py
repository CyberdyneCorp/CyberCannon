"""The two write tools, and the specified impossibility of a third (D3, D4).

`mcp-write-surface` fixes the number before it fixes the behaviour: *"exactly
two tools that change recorded state"*, and *"any tool that changes recorded
state and is not one of those two SHALL be treated as a defect rather than an
addition."* So this module exists mainly to be short, and to be the place
somebody has to edit — in front of a reviewer — to make it longer.

* **`add_annotation`** records an observation. It is the same shape every tool
  in this package has: arguments in, one container call, prose out. It takes no
  author and no agent, because *"the agent's identifier SHALL come from the
  launch configuration of the process, never from a tool parameter or the text
  of the write"* — there is no parameter here that could carry one, so the
  claimed author the specification forbids is not constructible rather than
  merely ignored.
* **`report_export`** delivers a verdict. It calls the same
  `validate_export` the artist's command line calls, hands *that* verdict to the
  reporting use case, and returns success whether or not the destination was
  reachable — because *"a failure to deliver ... SHALL NOT block or error the
  automated caller"*, and a tool whose success depended on a server's health
  would eventually be awaited by a pre-commit hook.

What is deliberately absent is the whole of the prohibition: there is no
promotion tool, no constraint parameter, no state parameter, no resolution and
no asset creation. An agent records that a budget is unreachable; the budget
does not move, because nothing in this file can move it.

The `result` argument of `report_export` is the caller's own account of what it
saw, and it is treated exactly as a claimed author is: recorded nowhere, and
powerless. The verdict that is reported is the one the local validator produces
from the local files, which is what makes *"the reported outcome SHALL be
identical to the verdict the same caller already received locally"* true by
construction rather than by trust.
"""

from __future__ import annotations

from cybercanon.adapters.inbound.mcp import rendering
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.results import Result, succeeded
from cybercanon.application.use_cases.observations import ObservationRequest, ReportedRun
from cybercanon.application.use_cases.validate_export import ValidationOutcome

WRITE_TOOL_NAMES: tuple[str, ...] = ("add_annotation", "report_export")
"""The tools that change recorded state. Two, and the number is the requirement.

Kept apart from the read surface's list so that the count can be asserted
directly: a test reads this tuple and fails if it ever has three entries, which
is the specified maximum wearing a type.
"""


def observation_from(
    asset: str, target: str, text: str, kind: str, observation_kind: str
) -> ObservationRequest:
    """The tool's arguments as the use case's request — a rename and nothing more.

    There is no identity, no author and no state in either shape, so this cannot
    lose or invent one. It is a function rather than an inline constructor so
    that the tool body stays one call wide.
    """
    return ObservationRequest(
        asset=asset, target=target, text=text, kind=kind, observation_kind=observation_kind
    )


def reported(container: Container, outcome: ValidationOutcome, export: str) -> Result[ReportedRun]:
    """Hand a verdict that already exists to the reporting use case.

    Nothing is evaluated here and nothing is decided: `outcome` arrived from the
    validation use case, and it is passed on unchanged.
    """
    return container.report_validation_outcome(outcome, export=export)


def answer_report(
    container: Container, validated: Result[ValidationOutcome], export: str, asset: str
) -> str:
    """The reporting tool's whole response: the verdict, then what became of it.

    A validation that could not run at all is a refusal like any other — an
    unreadable export or an asset with no specification — and it is rendered as
    one. Anything else is a verdict, and a verdict always comes back to the
    caller even when the delivery of it did not happen.
    """
    if not succeeded(validated):
        return rendering.render_failure(validated, container_nearest(container, asset))
    delivery = reported(container, validated.value, export)
    if not succeeded(delivery):
        return rendering.render_undelivered(validated.value, delivery)
    return rendering.render_report(validated.value, delivery.value)


def container_nearest(container: Container, asset: str) -> tuple[str, ...]:
    """The closest indexed identifiers to one nobody recognised, or none."""
    nearest = container.nearest_assets(asset)
    return nearest.value if succeeded(nearest) else ()


__all__ = [
    "WRITE_TOOL_NAMES",
    "answer_report",
    "container_nearest",
    "observation_from",
    "reported",
]
