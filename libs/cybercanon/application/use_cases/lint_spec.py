"""`lint_spec` — the structural checks over the specification files themselves.

`validate_export` asks whether a mesh honours its specification. This asks
whether the specification is *checkable at all*: descending LODs, a first LOD
within the triangle budget, one file per id within a project, and — the one D12
adds — a design state that resolves to neither a clip nor an explicit
`animated: false`, and therefore constrains nothing.

That last one is the whole reason this use case ships with the validator rather
than after it. `states: [idle, walk, fire]` looked like a specification and
enforced nothing; making it enforceable means some existing files become invalid
until their author declares a clip naming convention or an unanimated state, and
the only humane way to ask for that edit is a linter that names the state and
the missing piece.

Every check is a pure domain function. This module's job is to load the files,
give each finding a **file path** to go with the field location the domain
already names, and see across files for the one check no single file can answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cybercanon.application.ports.spec_store import LoadedSpec, ProjectConfig, SpecStore
from cybercanon.domain.actor_checks import check_mapping
from cybercanon.domain.spec_checks import SpecDeclaration, check_asset, check_duplicate_ids
from cybercanon.domain.violations import Severity, SpecViolation


@dataclass(frozen=True)
class LintFinding:
    """One structural violation, and the file it is in."""

    path: str
    violation: SpecViolation

    @property
    def rule_id(self) -> str:
        return self.violation.rule_id

    @property
    def severity(self) -> Severity:
        return self.violation.severity

    @property
    def subject(self) -> str:
        """Where in the file: `constraints.lods`, `design.states[walk]`, `id`."""
        return self.violation.subject

    @property
    def is_error(self) -> bool:
        return self.violation.severity is Severity.ERROR


@dataclass(frozen=True)
class LintReport:
    """What linting a set of specification files found.

    `mapping` is kept apart from `findings` rather than merged into them because
    `.canon/actors.yaml` is not a specification file: it is authored content
    validated in the same pass, so it must be able to fail the run (it counts
    towards :attr:`errors`) without being counted as one more asset that was
    checked.
    """

    checked: tuple[str, ...] = ()
    findings: tuple[LintFinding, ...] = ()
    mapping: tuple[LintFinding, ...] = ()

    @property
    def all_findings(self) -> tuple[LintFinding, ...]:
        """Everything this run found, whichever authored file it was in."""
        return (*self.findings, *self.mapping)

    @property
    def errors(self) -> tuple[LintFinding, ...]:
        return tuple(finding for finding in self.all_findings if finding.is_error)

    @property
    def warnings(self) -> tuple[LintFinding, ...]:
        return tuple(finding for finding in self.all_findings if not finding.is_error)

    @property
    def passed(self) -> bool:
        """Failing if and only if an `error`-severity finding exists — as elsewhere."""
        return not self.errors

    def findings_of(self, rule_id: str) -> tuple[LintFinding, ...]:
        return tuple(finding for finding in self.all_findings if finding.rule_id == rule_id)

    def findings_in(self, path: str) -> tuple[LintFinding, ...]:
        return tuple(finding for finding in self.all_findings if finding.path == path)


def lint_specs(paths: Sequence[str], *, spec_store: SpecStore) -> LintReport:
    """Lint one specification file or many.

    Many is not a convenience: `spec.duplicate_id` is invisible to a file
    examined on its own, so a linter that only ever sees one file cannot answer
    it. Loading warnings (an unrecognised field, D5) are findings here too — a
    typo stays visible without version skew ever being fatal.
    """
    loaded = tuple(spec_store.load(path) for path in paths)
    findings = (
        *_loading_findings(loaded),
        *_structural_findings(loaded, spec_store),
        *_duplicate_findings(loaded),
    )
    return LintReport(checked=tuple(spec.path for spec in loaded), findings=findings)


def lint_project(root: str, *, spec_store: SpecStore) -> LintReport:
    """Lint every specification at or below `root`, and the actor mapping with them.

    The mapping travels in the same pass because that is the requirement: an
    empty or contradictory `.canon/actors.yaml` has to be a visible defect in
    the check somebody already runs, not a report only an identity feature knows
    how to print. It needs no identity and no network to validate, exactly like
    every other file here.
    """
    report = lint_specs(spec_store.specs_under(root), spec_store=spec_store)
    return LintReport(
        checked=report.checked,
        findings=report.findings,
        mapping=lint_actor_mapping(root, spec_store=spec_store),
    )


def lint_actor_mapping(root: str = "", *, spec_store: SpecStore) -> tuple[LintFinding, ...]:
    """The structural checks over `.canon/actors.yaml` (D12).

    Two sources, one shape: the violations the store produced when it could not
    parse the file, and the checks the domain makes over a mapping it could.
    Both arrive as ordinary findings, so a duplicated email is reported the way
    a descending-LOD error is.
    """
    loaded = spec_store.load_actor_mapping(root)
    return tuple(
        LintFinding(path=loaded.path, violation=violation)
        for violation in (*loaded.violations, *check_mapping(loaded.mapping))
    )


def _loading_findings(specs: Sequence[LoadedSpec]) -> tuple[LintFinding, ...]:
    return tuple(
        LintFinding(path=spec.path, violation=warning)
        for spec in specs
        for warning in spec.warnings
    )


def _structural_findings(
    specs: Sequence[LoadedSpec], spec_store: SpecStore
) -> tuple[LintFinding, ...]:
    return tuple(
        LintFinding(path=spec.path, violation=violation)
        for spec in specs
        for violation in check_asset(spec.asset, _clip_naming(spec_store.load_project(spec.path)))
    )


def _duplicate_findings(specs: Sequence[LoadedSpec]) -> tuple[LintFinding, ...]:
    """The one check no single file can answer, attached to every file involved."""
    return tuple(
        LintFinding(path=path, violation=violation)
        for paths in _clashing_paths(specs)
        for violation in check_duplicate_ids(_declarations(specs, paths))
        for path in paths
    )


def _clashing_paths(specs: Sequence[LoadedSpec]) -> tuple[tuple[str, ...], ...]:
    """The path groups that declare the same id — a lookup, never a rule."""
    paths_by_id: dict[str, list[str]] = {}
    for spec in specs:
        paths_by_id.setdefault(spec.asset.id.value, []).append(spec.path)
    return tuple(tuple(sorted(paths)) for _, paths in sorted(paths_by_id.items()) if len(paths) > 1)


def _declarations(
    specs: Sequence[LoadedSpec], paths: tuple[str, ...]
) -> tuple[SpecDeclaration, ...]:
    return tuple(
        SpecDeclaration(path=spec.path, asset_id=spec.asset.id)
        for spec in specs
        if spec.path in paths
    )


def _clip_naming(project: ProjectConfig) -> str | None:
    return project.defaults.clip_naming if project.defaults else None


__all__ = [
    "LintFinding",
    "LintReport",
    "lint_actor_mapping",
    "lint_project",
    "lint_specs",
]
