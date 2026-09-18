"""The composition root: ports in, use cases out (D11).

Wiring happens **once**, here, and every inbound surface points at it. The CLI
that ships in this change, the FastMCP server of the next one and the FastAPI
app after that construct a :class:`Container` and call the same methods, which
is what makes "one verdict across every surface" structural rather than
aspirational — there is no second place a use case could be assembled
differently.

Two properties this module is shaped by:

* **It holds ports, never adapters.** Nothing here imports
  :mod:`cybercanon.adapters.outbound`; building the real adapters is
  :mod:`cybercanon.adapters.wiring.build`. That split is what lets an inbound
  adapter import the container type without acquiring an import of an outbound
  one, which import-linter forbids (D10) and which would otherwise make the CLI
  structurally dependent on `trimesh` being installed.
* **It adds no logic.** Every method is a one-line delegation to the use case of
  the same name. A branch here would be a rule living outside the domain, and
  :mod:`tests.tooling.test_rule_logic_stays_in_the_domain` fails the build over
  exactly that.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.mesh_inspector import MeshInspector
from cybercanon.application.ports.spec_store import ProjectConfig, SpecStore
from cybercanon.application.use_cases.compile_spec import (
    CompiledBriefing,
    CompiledSpec,
    compile_project_briefing,
    compile_spec,
)
from cybercanon.application.use_cases.lint_spec import LintReport, lint_project, lint_specs
from cybercanon.application.use_cases.validate_export import ValidationOutcome, validate_export

USE_CASES: tuple[str, ...] = (
    "validate_export",
    "lint_specs",
    "lint_project",
    "compile_spec",
    "compile_project_briefing",
)
"""Every use case this change ships, by the name the container resolves it under.

A test walks this tuple, so a use case added without a way to reach it from an
inbound adapter fails the build rather than waiting for someone to notice.
"""


@dataclass(frozen=True)
class Container:
    """The wired application: three ports, and every use case over them."""

    spec_store: SpecStore
    mesh_inspector: MeshInspector
    blob_store: BlobStore | None = None

    # -- validation ------------------------------------------------------

    def validate_export(self, export: str, *, emit_preview: bool = False) -> ValidationOutcome:
        """One export against its governing specification."""
        return validate_export(
            export,
            spec_store=self.spec_store,
            mesh_inspector=self.mesh_inspector,
            blob_store=self.blob_store,
            emit_preview=emit_preview,
        )

    # -- specification files ---------------------------------------------

    def lint_specs(self, paths: Sequence[str]) -> LintReport:
        """The structural checks over the specification files themselves."""
        return lint_specs(paths, spec_store=self.spec_store)

    def lint_project(self, root: str = "") -> LintReport:
        """The same checks over every specification at or below `root`."""
        return lint_project(root, spec_store=self.spec_store)

    # -- compilation -----------------------------------------------------

    def compile_spec(self, spec_path: str) -> CompiledSpec:
        """One asset's specification, compiled into its briefing."""
        return compile_spec(spec_path, spec_store=self.spec_store)

    def compile_project_briefing(self, root: str = "") -> CompiledBriefing:
        """The project's standing rules, with no asset in them."""
        return compile_project_briefing(root, spec_store=self.spec_store)

    # -- discovery (D9) --------------------------------------------------

    def discover(self, path: str) -> str | None:
        """The governing specification for a path, or ``None`` — never an error.

        The port owns the walk; this is the one call an inbound adapter makes
        when it has to group changed files by the asset that owns them, so the
        CLI still does no path arithmetic of its own.
        """
        return self.spec_store.discover(path)

    def project(self, root: str = "") -> ProjectConfig:
        """The project configuration governing `root`."""
        return self.spec_store.load_project(root)


__all__ = ["USE_CASES", "Container"]
