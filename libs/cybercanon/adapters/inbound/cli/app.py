"""The `canon` commands — argument translation, and nothing else (D11).

Four commands, each the same three lines: turn arguments into paths, call one
use case on the container, hand the result to a renderer. **No rule, no
threshold, no severity and no merge appears in this module**, and
`tests/tooling/test_rule_logic_stays_in_the_domain.py` fails the build if one
ever does — because the moment the CLI decides something the web button does
not, the product has the bug it exists to prevent.

* `canon validate EXPORT...` — one export, or several, against their
  specifications.
* `canon compile SPEC` — `asset.yaml` in, `art-spec.md` out.
* `canon check [PATH]` — the structural checks over the specification files
  themselves, plus whatever the project configuration got wrong.
* `canon changed FILE...` — the pre-commit entry point: validate only the assets
  the changed files belong to, and exit `0` when none of them belong to one.

Two seams, each existing exactly once:

* **Exit codes** — :func:`_run` is the only place a process exit is decided, and
  the only `except OperationFailed` in the CLI (`0` clean, `1` error-severity
  violations, `2` could not run).
* **Output** — :func:`_emit` is the only place anything is written. In
  `--json` mode standard output carries the structured document and nothing
  else; prose, diagnostics and failures go to standard error.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from cybercanon.adapters.inbound.cli import payload as payloads
from cybercanon.adapters.inbound.cli import rendering
from cybercanon.adapters.inbound.cli.exit_codes import COULD_NOT_RUN, exit_code
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.errors import OperationFailed
from cybercanon.application.use_cases.compile_spec import COMPILED_FILENAME
from cybercanon.application.use_cases.lint_spec import LintReport
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.violations import SpecViolation

HELP = """\
CyberCanon — the versioned canon of a game project.

Validation, checking and compilation need no login, no token and no network.
"""

NOTHING_TO_DO = "canon: no changed file belongs to an asset"

JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Write only the structured result to standard output."),
]
PreviewOption = Annotated[
    bool,
    typer.Option("--preview", help="Also emit a preview; its failure never changes the verdict."),
]


@dataclass(frozen=True)
class Produced:
    """What a command produced: the same result as data, as prose, and as a verdict."""

    payload: dict[str, Any]
    text: str
    passed: bool


def build_app(container: Container) -> typer.Typer:
    """The `canon` application, wired to one container.

    The container is a parameter rather than a module global because that is
    what makes the CLI testable against in-memory fakes with no repository on
    disk — the same container the MCP server and the HTTP app will be handed.
    """
    app = typer.Typer(add_completion=False, help=HELP, no_args_is_help=True)

    @app.command()
    def validate(
        exports: Annotated[list[Path], typer.Argument(help="Export files to validate.")],
        json_output: JsonOption = False,
        preview: PreviewOption = False,
    ) -> None:
        """Validate exports against the specifications that govern them."""
        _run("validate", json_output, lambda: _validate(container, exports, preview))

    @app.command(name="compile")
    def compile_spec(
        spec: Annotated[Path, typer.Argument(help="The `asset.yaml` to compile.")],
        out: Annotated[Path | None, typer.Option("--out", help="Where to write it.")] = None,
        to_stdout: Annotated[
            bool, typer.Option("--stdout", help="Write the briefing to standard output.")
        ] = False,
        json_output: JsonOption = False,
    ) -> None:
        """Compile a specification into its readable `art-spec.md`."""
        _run("compile", json_output, lambda: _compile(container, spec, out, to_stdout))

    @app.command()
    def check(
        path: Annotated[Path, typer.Argument(help="Where to look for specifications.")] = Path(),
        json_output: JsonOption = False,
    ) -> None:
        """Check that specification files are themselves structurally valid."""
        _run("check", json_output, lambda: _check(container, path))

    @app.command()
    def changed(
        files: Annotated[list[Path], typer.Argument(help="The changed files.")],
        json_output: JsonOption = False,
    ) -> None:
        """Validate only the assets a list of changed files belongs to."""
        _run("changed", json_output, lambda: _changed(container, files))

    return app


# --------------------------------------------------------------------------
# The two seams
# --------------------------------------------------------------------------


def _run(command: str, json_output: bool, operation: Callable[[], Produced]) -> None:
    """The exit-code seam: the only place this process decides how it ends (D11)."""
    try:
        produced = operation()
    except OperationFailed as error:
        failed = payloads.failure_payload(command, error)
        _emit(json_output, failed, rendering.render_failure(error), diagnostic=True)
        raise typer.Exit(COULD_NOT_RUN) from None
    _emit(json_output, produced.payload, produced.text)
    raise typer.Exit(exit_code(produced.passed))


def _emit(
    json_output: bool, payload: dict[str, Any], text: str, *, diagnostic: bool = False
) -> None:
    """The output seam: structured on standard output, prose everywhere else."""
    if json_output:
        print(json.dumps(payload, indent=2), file=sys.stdout)
        if diagnostic:
            print(text, file=sys.stderr)
        return
    print(text, file=sys.stderr if diagnostic else sys.stdout)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _validate(container: Container, exports: Sequence[Path], preview: bool) -> Produced:
    outcomes = [
        container.validate_export(export, emit_preview=preview)
        for export in _repo_paths(container, exports)
    ]
    return Produced(
        payload=payloads.validation_payload(outcomes),
        text=rendering.render_validations(outcomes),
        passed=all(outcome.passed for outcome in outcomes),
    )


def _compile(container: Container, spec: Path, out: Path | None, to_stdout: bool) -> Produced:
    (path,) = _repo_paths(container, (spec,))
    compiled = container.compile_spec(path)
    destination = None if to_stdout else _destination(container, compiled.source, out)
    written = None if destination is None else str(destination)
    if destination is not None:
        _write(destination, compiled.text)
    text = compiled.text if written is None else rendering.render_compiled(compiled.source, written)
    return Produced(
        payload=payloads.compile_payload(compiled, written),
        text=text,
        passed=True,
    )


def _check(container: Container, path: Path) -> Produced:
    (root,) = _repo_paths(container, (path,))
    report = container.lint_project(root)
    notes = container.project(root).warnings
    return Produced(
        payload=payloads.lint_payload(report, notes),
        text=_check_text(report, notes),
        passed=report.passed,
    )


def _changed(container: Container, files: Sequence[Path]) -> Produced:
    specs, exports = _owning_assets(container, files)
    if not specs:
        return Produced(payload=payloads.nothing_changed_payload(), text=NOTHING_TO_DO, passed=True)
    lint = container.lint_specs(specs)
    outcomes = [container.validate_export(export) for export in exports]
    passed = lint.passed and all(outcome.passed for outcome in outcomes)
    return Produced(
        payload=payloads.changed_payload(specs, outcomes, lint),
        text=_changed_text(lint, outcomes),
        passed=passed,
    )


# --------------------------------------------------------------------------
# Translation helpers — paths in, text out. No decisions.
# --------------------------------------------------------------------------


def _owning_assets(
    container: Container, files: Sequence[Path]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The specifications the changed files belong to, and the exports among them.

    Discovery is the port's (D9); all this does is ask it once per file and keep
    the answers in a deterministic order. A file governed by no specification is
    dropped, which is the pre-commit hook's ordinary case.
    """
    governed = tuple(
        (path, spec)
        for path in _repo_paths(container, files)
        if (spec := container.discover(path)) is not None
    )
    specs = sorted({spec for _, spec in governed})
    exports = tuple(path for path, _ in governed if _is_export(path))
    return tuple(specs), exports


def _is_export(path: str) -> bool:
    """Whether a changed file is a mesh export — the format table answers, not the CLI."""
    return MeshFormat.from_name(Path(path).suffix) is not None


def _repo_paths(container: Container, paths: Sequence[Path]) -> tuple[str, ...]:
    """User paths as the store speaks them: repository-relative POSIX where possible.

    A path a person types is relative to the directory they are standing in; a
    path the store speaks is relative to the repository root. Resolving here is
    the whole of the CLI's path handling — the upward walk itself stays in the
    port.
    """
    root = Path(container.project().root or ".").resolve()
    return tuple(_relative(Path(path).resolve(), root) for path in paths)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _destination(container: Container, source: str, out: Path | None) -> Path:
    """Where a compiled briefing is written: beside its specification by default."""
    if out is not None:
        return out
    root = Path(container.project().root or ".")
    return root / Path(source).parent / COMPILED_FILENAME


def _write(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _check_text(report: LintReport, notes: Sequence[SpecViolation]) -> str:
    rendered = rendering.render_lint(report)
    if not notes:
        return rendered
    return "\n\n".join((rendering.render_project_notes(notes), rendered))


def _changed_text(lint: LintReport, outcomes: Sequence[ValidationOutcome]) -> str:
    blocks = [rendering.render_lint(lint)]
    if outcomes:
        blocks.append(rendering.render_validations(outcomes))
    return "\n\n".join(blocks)


__all__ = ["HELP", "NOTHING_TO_DO", "Produced", "build_app"]
