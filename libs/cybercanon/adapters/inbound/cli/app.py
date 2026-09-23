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
* `canon add-view ASSET IMAGE --slot NAME` — a concept view into the working
  copy, committed in the acting person's name. It is the *same use case* the
  ingestion endpoint calls, which is what makes the two produce the same
  commit; what differs is only the working copy underneath — the person's own
  checkout here, the hosted volume there.
* `canon describe ASSET` and `canon suggest-aliases ASSET` — generate a
  description, tags and suggested aliases for an asset's concept views. Both
  exit `0` and say so when no model is configured, because the feature is
  optional by construction and a pre-commit hook must not start failing when a
  gateway goes down.
* `canon accept-alias ASSET VALUE --image HASH` and `canon reject-alias` — the
  two exits a proposal has. Acceptance writes one alias into `asset.yaml` as a
  commit in the accepting person's name; rejection writes nothing and records
  that the term is not to be offered again for that image.
* `canon index rebuild|misses` — maintenance of the derived index, and the
  zero-result search terms it recorded locally (D11).
* `canon views rebuild` — re-mirror every concept view and re-derive its
  thumbnails. Both are derived from the repository by specification, so this is
  the documented recovery rather than a repair.
* `canon actors unmapped` — the git authors and recorded owners
  `.canon/actors.yaml` does not bind yet, listed so the file can be completed.
* `canon auth login|logout|status` — the device-authorization sign-in, the
  credential stored in the operating system's credential store rather than in
  any file, and its removal. **Nothing else in `canon` needs it**: validation,
  checking and compilation complete on a machine that has never signed in.
* `canon mcp serve` — the FastMCP read server over standard input and output,
  built from the same container every other command here runs against.

Two seams, each existing exactly once:

* **Exit codes** — :func:`_run` is the only place a process exit is decided (`0`
  clean, `1` error-severity violations, `2` could not run). A use case now
  *returns* its refusal rather than raising it (D10), so what :func:`_run` reads
  is a :class:`~cybercanon.application.results.Result`; the single
  `except OperationFailed` it keeps is for the two port calls this module makes
  outside a use case — reading the project configuration and asking discovery
  which asset owns a changed file — and it puts them into the same vocabulary
  through :func:`~cybercanon.application.results.classify` rather than beside it.
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
from cybercanon.application.results import Ok, Result, classify, first_refusal, succeeded
from cybercanon.application.use_cases.compile_spec import COMPILED_FILENAME
from cybercanon.application.use_cases.hosted_repository import author_for
from cybercanon.application.use_cases.ingest_views import UploadedImage
from cybercanon.application.use_cases.lint_spec import LintReport
from cybercanon.application.use_cases.validate_export import ValidationOutcome
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.violations import SpecViolation

HELP = """\
CyberCanon — the versioned canon of a game project.

Validation, checking and compilation need no login, no token and no network.
"""

NOTHING_TO_DO = "canon: no changed file belongs to an asset"

INDEX_HELP = "Maintain the derived lookup index, and read what it recorded."
VIEWS_HELP = """\
Concept views: bring one in, and rebuild what derives from them.

The mirror and the thumbnails are both droppable by specification — the views
themselves are files in the repository — so `views rebuild` is a recovery
somebody runs rather than a repair somebody hopes for.
"""
ACTORS_HELP = "The people a project's `.canon/actors.yaml` does or does not bind."
AUTH_HELP = """\
Sign in to CyberdyneAuth, or sign out again.

The credential is kept in the operating system's credential store and never in
a file inside the repository. Validation, checking and compilation need none of
this and work on a machine that has never signed in.
"""
MCP_HELP = "The local read server an agent client spawns over standard input and output."

ContainerFor = Callable[[Path], Container]
"""How a command opens a *different* repository from the one the app was built for.

Only `mcp serve` needs it — an agent client names the project directory in its
configuration rather than being able to choose a working directory. It is a
parameter because the inbound CLI may not import an outbound adapter (D10), so
the process entry point is the one that knows how a container is built.
"""

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


Command = Callable[[], Result[Produced]]
"""One command's work: either what it produced, or the refusal that stopped it."""


def build_app(container: Container, container_for: ContainerFor | None = None) -> typer.Typer:
    """The `canon` application, wired to one container.

    The container is a parameter rather than a module global because that is
    what makes the CLI testable against in-memory fakes with no repository on
    disk — the same container the MCP server and the HTTP app will be handed.

    `container_for` opens another repository by path, and defaults to *this
    one*: a test builds the app over fakes and `canon mcp serve` still serves
    them, while the installed binary passes the composition root and
    `canon mcp serve /path/to/game` serves that working copy.
    """
    open_project: ContainerFor = container_for or (lambda _root: container)
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

    @app.command(name="add-view")
    def add_view(
        asset: Annotated[str, typer.Argument(help="The asset the view belongs to.")],
        image: Annotated[Path, typer.Argument(help="The image file to ingest.")],
        slot: Annotated[
            str, typer.Option("--slot", help="Which view of the asset this is.")
        ] = "front",
        name: Annotated[
            str, typer.Option("--name", help="The asset's name, when the upload creates it.")
        ] = "",
        json_output: JsonOption = False,
    ) -> None:
        """Ingest a concept view, committed to this working copy in your name."""
        _run("add-view", json_output, lambda: _add_view(container, asset, slot, image, name))

    @app.command()
    def describe(
        asset: Annotated[str, typer.Argument(help="The asset to describe.")],
        slot: Annotated[
            str, typer.Option("--slot", help="Only this view, rather than every one.")
        ] = "",
        json_output: JsonOption = False,
    ) -> None:
        """Generate a description, tags and suggested aliases for an asset's views."""
        _run("describe", json_output, lambda: _describe(container, asset, slot))

    @app.command(name="suggest-aliases")
    def suggest_aliases(
        asset: Annotated[str, typer.Argument(help="The asset to propose aliases for.")],
        slot: Annotated[
            str, typer.Option("--slot", help="Only this view, rather than every one.")
        ] = "",
        json_output: JsonOption = False,
    ) -> None:
        """Propose search terms for an asset. Nothing is written until you accept one."""
        _run("suggest-aliases", json_output, lambda: _suggest(container, asset, slot))

    @app.command(name="accept-alias")
    def accept_alias(
        asset: Annotated[str, typer.Argument(help="The asset the alias belongs to.")],
        value: Annotated[str, typer.Argument(help="The suggested alias to accept.")],
        image: Annotated[
            str, typer.Option("--image", help="The image hash the suggestion came from.")
        ],
        edited: Annotated[
            str, typer.Option("--as", help="Accept this instead of the suggested wording.")
        ] = "",
        json_output: JsonOption = False,
    ) -> None:
        """Write one suggested alias into `asset.yaml`, committed in your name."""
        _run(
            "accept-alias",
            json_output,
            lambda: _accept(container, asset, image, value, edited),
        )

    @app.command(name="reject-alias")
    def reject_alias(
        asset: Annotated[str, typer.Argument(help="The asset the suggestion is about.")],
        value: Annotated[str, typer.Argument(help="The suggested alias to refuse.")],
        image: Annotated[
            str, typer.Option("--image", help="The image hash the suggestion came from.")
        ],
        json_output: JsonOption = False,
    ) -> None:
        """Refuse one suggestion for one image. It is not offered again."""
        _run("reject-alias", json_output, lambda: _reject(container, asset, image, value))

    views_app = typer.Typer(add_completion=False, help=VIEWS_HELP, no_args_is_help=True)
    index_app = typer.Typer(add_completion=False, help=INDEX_HELP, no_args_is_help=True)
    actors_app = typer.Typer(add_completion=False, help=ACTORS_HELP, no_args_is_help=True)
    auth_app = typer.Typer(add_completion=False, help=AUTH_HELP, no_args_is_help=True)
    mcp_app = typer.Typer(add_completion=False, help=MCP_HELP, no_args_is_help=True)
    app.add_typer(views_app, name="views")
    app.add_typer(index_app, name="index")
    app.add_typer(actors_app, name="actors")
    app.add_typer(auth_app, name="auth")
    app.add_typer(mcp_app, name="mcp")

    @views_app.command(name="rebuild")
    def rebuild_views(json_output: JsonOption = False) -> None:
        """Re-mirror every concept view and re-derive its thumbnails."""
        _run("views rebuild", json_output, lambda: _rebuild_views(container))

    @index_app.command(name="rebuild")
    def rebuild(
        path: Annotated[Path, typer.Argument(help="Where to look for specifications.")] = Path(),
        json_output: JsonOption = False,
    ) -> None:
        """Rescan the specifications and rewrite the project's index rows."""
        _run("index rebuild", json_output, lambda: _rebuild(container, path))

    @index_app.command(name="misses")
    def misses(json_output: JsonOption = False) -> None:
        """The search terms that matched nothing, as recorded on this machine."""
        _run("index misses", json_output, lambda: _misses(container))

    @actors_app.command(name="unmapped")
    def unmapped(
        path: Annotated[Path, typer.Argument(help="Where the project lives.")] = Path(),
        json_output: JsonOption = False,
    ) -> None:
        """List the git authors and owners `.canon/actors.yaml` does not bind."""
        _run("actors unmapped", json_output, lambda: _unmapped(container, path))

    @auth_app.command(name="login")
    def login(json_output: JsonOption = False) -> None:
        """Sign in by approving a device authorization in a browser."""
        _run("auth login", json_output, lambda: _login(container, json_output))

    @auth_app.command(name="logout")
    def logout(json_output: JsonOption = False) -> None:
        """Remove the credential this machine stored. Twice is not an error."""
        _run("auth logout", json_output, lambda: _logout(container))

    @auth_app.command(name="status")
    def status(json_output: JsonOption = False) -> None:
        """Whether this machine holds a credential — never what it is."""
        _run("auth status", json_output, lambda: _status(container))

    @mcp_app.command(name="serve")
    def serve(
        path: Annotated[Path, typer.Argument(help="The project directory to serve.")] = Path(),
    ) -> None:
        """Serve this project's canon to an agent client over standard input and output."""
        _serve(open_project(path))

    return app


# --------------------------------------------------------------------------
# The two seams
# --------------------------------------------------------------------------


def _run(command: str, json_output: bool, operation: Command) -> None:
    """The exit-code seam: the only place this process decides how it ends (D11)."""
    result = _attempted(operation)
    if not succeeded(result):
        failed = payloads.failure_payload(command, result)
        _emit(json_output, failed, rendering.render_failure(result), diagnostic=True)
        raise typer.Exit(COULD_NOT_RUN)
    produced = result.value
    _emit(json_output, produced.payload, produced.text)
    raise typer.Exit(exit_code(produced.passed))


def _attempted(operation: Command) -> Result[Produced]:
    """The command's answer, with a port failure put into the same vocabulary.

    The CLI reads two things through the container that are not use cases — the
    project configuration, for the directory a path is relative to, and
    discovery, for which asset a changed file belongs to. Both are port calls and
    both still raise, so this is where they join the outcome union rather than
    bypassing it.
    """
    try:
        return operation()
    except OperationFailed as error:
        return classify(error)


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


def _validate(container: Container, exports: Sequence[Path], preview: bool) -> Result[Produced]:
    results = tuple(
        container.validate_export(export, emit_preview=preview)
        for export in _repo_paths(container, exports)
    )
    refused = first_refusal(results)
    if refused is not None:
        return refused
    outcomes = [result.value for result in results if succeeded(result)]
    return Ok(
        Produced(
            payload=payloads.validation_payload(outcomes),
            text=rendering.render_validations(outcomes),
            passed=all(outcome.passed for outcome in outcomes),
        )
    )


def _compile(
    container: Container, spec: Path, out: Path | None, to_stdout: bool
) -> Result[Produced]:
    (path,) = _repo_paths(container, (spec,))
    result = container.compile_spec(path)
    if not succeeded(result):
        return result
    compiled = result.value
    destination = None if to_stdout else _destination(container, compiled.source, out)
    written = None if destination is None else str(destination)
    if destination is not None:
        _write(destination, compiled.text)
    text = compiled.text if written is None else rendering.render_compiled(compiled.source, written)
    return Ok(
        Produced(
            payload=payloads.compile_payload(compiled, written),
            text=text,
            passed=True,
        )
    )


def _check(container: Container, path: Path) -> Result[Produced]:
    (root,) = _repo_paths(container, (path,))
    result = container.lint_project(root)
    if not succeeded(result):
        return result
    report = result.value
    notes = container.project(root).warnings
    return Ok(
        Produced(
            payload=payloads.lint_payload(report, notes),
            text=_check_text(report, notes),
            passed=report.passed,
        )
    )


def _add_view(
    container: Container, asset: str, slot: str, image: Path, name: str
) -> Result[Produced]:
    """One image into one slot — the same use case the ingestion endpoint calls.

    The author is resolved exactly as every other write resolves one: the acting
    person through `.canon/actors.yaml` (D5). A person with no entry is refused
    *naming the missing entry*, here as over HTTP, because committing concept
    art under a shared identity is how `git blame` stops answering the question
    the tool exists to answer.
    """
    identity = author_for(container.resolve_actor(), container.spec_store)
    uploads = [UploadedImage(slot=slot, content=_bytes(image), filename=image.name)]
    result = container.add_views(
        asset, uploads, author=identity.author, subject=identity.actor.subject, name=name
    )
    if not succeeded(result):
        return result
    outcome = result.value
    return Ok(
        Produced(
            payload=payloads.ingest_payload(outcome),
            text=rendering.render_ingestion(outcome),
            passed=True,
        )
    )


def _describe(container: Container, asset: str, slot: str) -> Result[Produced]:
    """Generation, and an unavailable model is an ordinary successful answer.

    `llm-integration` requires the feature to *report itself unavailable* with
    everything else working, so a deployment with no model exits `0` with the
    reason on standard output rather than exiting `2` — which would make an
    optional feature look like a broken installation in somebody's pre-commit
    hook.
    """
    return _derived("describe", container.describe_views(asset, slot=slot, actor=_actor(container)))


def _suggest(container: Container, asset: str, slot: str) -> Result[Produced]:
    return _derived(
        "suggest-aliases", container.suggest_aliases(asset, slot=slot, actor=_actor(container))
    )


def _derived(command: str, result: Result[Any]) -> Result[Produced]:
    if not succeeded(result):
        return result
    described = result.value
    return Ok(
        Produced(
            payload=payloads.derived_payload(command, described),
            text=rendering.render_derived(described),
            passed=True,
        )
    )


def _accept(
    container: Container, asset: str, image: str, value: str, edited: str
) -> Result[Produced]:
    """The bridge: one proposal becomes one authored alias, committed as you.

    The author is resolved exactly as every other write resolves one — the
    acting person through `.canon/actors.yaml` — so a person with no entry is
    refused naming the missing entry rather than committing under a shared
    identity.
    """
    identity = author_for(container.resolve_actor(), container.spec_store)
    result = container.accept_suggested_alias(
        asset, image, value, written=edited, actor=identity.actor, author=identity.author
    )
    if not succeeded(result):
        return result
    accepted = result.value
    return Ok(
        Produced(
            payload=payloads.acceptance_payload(accepted),
            text=rendering.render_acceptance(accepted),
            passed=True,
        )
    )


def _reject(container: Container, asset: str, image: str, value: str) -> Result[Produced]:
    identity = author_for(container.resolve_actor(), container.spec_store)
    result = container.reject_suggested_alias(
        asset, image, value, actor=identity.actor, author=identity.author
    )
    if not succeeded(result):
        return result
    rejected = result.value
    return Ok(
        Produced(
            payload=payloads.rejection_payload(rejected),
            text=rendering.render_rejection(rejected),
            passed=True,
        )
    )


def _actor(container: Container):
    """Who is asking. Generation needs no permission, but a record needs a name."""
    return container.resolve_actor().actor


def _bytes(image: Path) -> bytes:
    """The file's bytes. The only file this command reads, and it reads it whole."""
    return image.read_bytes()


def _rebuild_views(container: Container) -> Result[Produced]:
    """Task 3.5's command: the mirror, rebuilt from the repository alone."""
    result = container.rebuild_view_mirror()
    if not succeeded(result):
        return result
    report = result.value
    return Ok(
        Produced(
            payload=payloads.view_mirror_payload(report),
            text=rendering.render_view_mirror(report),
            passed=True,
        )
    )


def _rebuild(container: Container, path: Path) -> Result[Produced]:
    (root,) = _repo_paths(container, (path,))
    result = container.rebuild_index(root)
    if not succeeded(result):
        return result
    report = result.value
    return Ok(
        Produced(
            payload=payloads.rebuild_payload(report),
            text=rendering.render_rebuild(report),
            passed=report.is_complete,
        )
    )


def _misses(container: Container) -> Result[Produced]:
    result = container.recorded_misses()
    if not succeeded(result):
        return result
    recorded = result.value
    return Ok(
        Produced(
            payload=payloads.misses_payload(recorded),
            text=rendering.render_misses(recorded),
            passed=True,
        )
    )


def _unmapped(container: Container, path: Path) -> Result[Produced]:
    (root,) = _repo_paths(container, (path,))
    result = container.unmapped_authors(root)
    if not succeeded(result):
        return result
    authors = result.value
    return Ok(
        Produced(
            payload=payloads.unmapped_payload(authors),
            text=rendering.render_unmapped(authors),
            passed=not authors.violations,
        )
    )


def _login(container: Container, json_output: bool) -> Result[Produced]:
    """Sign in, showing the person what to approve while the process waits.

    The announcement goes to standard error even in `--json` mode, because the
    structured document is the *result* and this is an instruction the person
    has to act on before there is one.
    """

    def announce(grant) -> None:
        print(rendering.render_device_grant(grant), file=sys.stderr)

    result = container.sign_in(announce)
    if not succeeded(result):
        return result
    signed_in = result.value
    return Ok(
        Produced(
            payload=payloads.sign_in_payload(signed_in),
            text=rendering.render_sign_in(signed_in),
            passed=True,
        )
    )


def _logout(container: Container) -> Result[Produced]:
    result = container.sign_out()
    if not succeeded(result):
        return result
    signed_out = result.value
    return Ok(
        Produced(
            payload=payloads.sign_out_payload(signed_out),
            text=rendering.render_sign_out(signed_out),
            passed=True,
        )
    )


def _status(container: Container) -> Result[Produced]:
    result = container.sign_in_status()
    if not succeeded(result):
        return result
    status = result.value
    return Ok(
        Produced(
            payload=payloads.sign_in_status_payload(status),
            text=rendering.render_sign_in_status(status),
            passed=True,
        )
    )


def _serve(container: Container) -> None:
    """Hand one container to the read server and let it own the process.

    The import is local because it is the only thing in `canon` that needs
    FastMCP: a validator run by a pre-commit hook should not pay for importing a
    server it will never start. Nothing is printed — standard output is the
    transport, and a stray line on it would corrupt the protocol.
    """
    from cybercanon.adapters.inbound.mcp import tools

    tools.serve(container)


def _changed(container: Container, files: Sequence[Path]) -> Result[Produced]:
    specs, exports = _owning_assets(container, files)
    if not specs:
        return Ok(
            Produced(payload=payloads.nothing_changed_payload(), text=NOTHING_TO_DO, passed=True)
        )
    attempted = (container.lint_specs(specs), *(container.validate_export(e) for e in exports))
    refused = first_refusal(attempted)
    if refused is not None:
        return refused
    lint, *validated = [result.value for result in attempted if succeeded(result)]
    passed = lint.passed and all(outcome.passed for outcome in validated)
    return Ok(
        Produced(
            payload=payloads.changed_payload(specs, validated, lint),
            text=_changed_text(lint, validated),
            passed=passed,
        )
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


__all__ = [
    "ACTORS_HELP",
    "AUTH_HELP",
    "HELP",
    "INDEX_HELP",
    "MCP_HELP",
    "NOTHING_TO_DO",
    "ContainerFor",
    "Produced",
    "build_app",
]
