"""What one validation run leaves behind, and when that is worth a commit (G2).

`openspec/project.md`'s gate decision G2 settles where a validation outcome
durably lives: *"A validation outcome is repository content, written as a file
beside the asset and committed by the worker."* It is forced rather than chosen
— `hosted-repository` requires that no write reach only the index, `asset-spec`
requires that dropping the index loses nothing, and `asset-lookup` requires
`where_is` to report which export was validated and when. An index row satisfies
none of those.

This module is the domain half of that decision and it is deliberately small:

* :class:`ValidationRecord` — what was validated, what it hashed to, what the
  verdict was, when, and who it is attributed to. A value object, so the whole
  writer suite runs with no repository and no mesh;
* :func:`needs_validation` — whether a run is worth doing at all, which is the
  export's digest or its governing specification's having moved since the
  recorded outcome;
* :func:`needs_commit` — G2's mitigation, in one function: *"Mitigated by
  committing only when the verdict or the export hash changes, so a repeated run
  of an unchanged export writes nothing."*

Both decisions are here rather than in the worker for the reason every decision
in this product is: a worker that decided when to commit would be a second
opinion about what a validation outcome is, and the next surface that reports
one would derive a third.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

AUTOMATION = "automation"
"""Who an outcome is attributed to when no person reported it.

G2: *"Attribution: the reporting actor, or automation when there is no person."*
A fetch-triggered run has no live caller, so it is recorded as automation rather
than as the last person who happened to touch the asset.
"""

AUTOMATION_AUTHOR_NAME = "canon automation"
AUTOMATION_AUTHOR_EMAIL = "automation@cybercanon.invalid"
"""The git identity a personless validation commit is authored with.

Deliberately in the reserved `.invalid` top-level domain, so this address can
never collide with a real person's and can never be mistaken for one in
`.canon/actors.yaml`. D8's refusal — *"no mapping, no write"* — is about a
**person** whose edits would otherwise be attributed to somebody else; a run
with no person has nobody to misattribute, and G2 names automation as its
attribution in so many words.
"""

PASSED = "passed"
FAILED = "failed"


@dataclass(frozen=True)
class ValidationRecord:
    """One validation run, as the repository holds it beside the asset.

    `export_hash` and `spec_hash` are what make the two decisions below cheap:
    the first says whether the thing that was validated has moved, the second
    whether the rules it was validated against have. Neither is an optimisation
    — without them a fetch would re-read every mesh in the repository, and with
    only the first a promoted constraint would never be enforced against an
    export nobody re-exported.
    """

    asset_id: str
    export: str
    export_hash: str
    passed: bool
    validated_at: datetime
    spec_hash: str = ""
    attributed_to: str = AUTOMATION
    performed_by: str = ""
    errors: int = 0
    warnings: int = 0

    @property
    def verdict(self) -> str:
        """The word a commit message and a briefing both use for the outcome."""
        return PASSED if self.passed else FAILED

    @property
    def by_automation(self) -> bool:
        return self.attributed_to == AUTOMATION


def needs_validation(
    recorded: ValidationRecord | None,
    *,
    export: str,
    export_hash: str,
    spec_hash: str = "",
) -> bool:
    """Whether this export is worth validating again (G1).

    G1 says the worker runs *"when the hosted working copy fetches a changed
    export"*, so an export whose bytes are the ones the recorded outcome was
    taken of is not re-read — which is what keeps a fetch from costing a full
    mesh load per asset on a repository where nothing moved.

    The specification is compared too, and that is not scope creep: a promoted
    constraint changes the verdict without changing one byte of the export, and
    an outcome that only ever refreshed when an artist re-exported would report
    a pass against a rule that no longer exists.
    """
    if recorded is None:
        return True
    return (
        recorded.export != export
        or recorded.export_hash != export_hash
        or recorded.spec_hash != spec_hash
    )


def needs_commit(recorded: ValidationRecord | None, current: ValidationRecord) -> bool:
    """Whether this outcome is different enough from the recorded one to commit (G2).

    *"Committing only when the verdict or the export hash changes, so a repeated
    run of an unchanged export writes nothing."* The export it concerns is
    compared as well, because an outcome that named a different file is a
    different answer to *which export was validated* even when the verdict and
    the digest coincide.

    The validation time is deliberately **not** compared. It moves on every run,
    so comparing it would make the mitigation vacuous and put a commit in the
    history for every tick of the fetch timer.
    """
    if recorded is None:
        return True
    return (
        recorded.passed != current.passed
        or recorded.export_hash != current.export_hash
        or recorded.export != current.export
    )


__all__ = [
    "AUTOMATION",
    "AUTOMATION_AUTHOR_EMAIL",
    "AUTOMATION_AUTHOR_NAME",
    "FAILED",
    "PASSED",
    "ValidationRecord",
    "needs_commit",
    "needs_validation",
]
