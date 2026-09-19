"""`compile_spec` — `asset.yaml` in, `art-spec.md` out, byte for byte.

The compiler and the validator consume the identical `EffectiveSpec` (D3), so
the briefing a person reads and the contract the validator enforces are the same
object rendered two ways and cannot drift. That is the entire reason compilation
is a use case rather than a template in an adapter.

Three properties the spec demands and the tests hold this to:

* **Deterministic** — compiling the same specification twice is byte-identical.
  Nothing here reads a clock, a host name, an environment variable or a random
  source; the rendering iterates fixed field orders (see `briefing`).
* **Offline** — the only collaborators are the specification file and the
  project configuration. No identity, no network, no derived store. Compilation
  works on a train.
* **Derived** — the output is returned, never read back in. An `art-spec.md`
  edited by hand is overwritten by the next compile because it was never an
  input; the writer lives in the CLI, where the file system belongs.
"""

from __future__ import annotations

from dataclasses import dataclass

from cybercanon.application.ports.spec_store import SpecStore
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.briefing import (
    render_asset_briefing,
    render_project_briefing,
)
from cybercanon.domain.effective_spec import EffectiveSpec, merge

COMPILED_FILENAME = "art-spec.md"


@dataclass(frozen=True)
class CompiledSpec:
    """One compiled briefing: the text, and what it was derived from."""

    asset_id: str
    source: str
    text: str
    spec: EffectiveSpec

    @property
    def filename(self) -> str:
        """What a writer names it, next to the specification it came from."""
        return COMPILED_FILENAME


@dataclass(frozen=True)
class CompiledBriefing:
    """The project-wide briefing: standing rules with no asset in them."""

    project: str | None
    text: str


@as_result
def compile_spec(spec_path: str, *, spec_store: SpecStore) -> CompiledSpec:
    """Compile one asset's specification into its briefing."""
    loaded = spec_store.load(spec_path)
    project = spec_store.load_project(spec_path)
    spec = merge(loaded.asset, project.defaults)
    return CompiledSpec(
        asset_id=loaded.asset.id.value,
        source=loaded.path,
        text=render_asset_briefing(loaded.asset, spec, source=loaded.path),
        spec=spec,
    )


@as_result
def compile_project_briefing(root: str = "", *, spec_store: SpecStore) -> CompiledBriefing:
    """Compile the project's standing rules alone — no asset's concept, no annotations.

    This is what an agent or a person is handed when the question is "what does
    this project always require", and it is deliberately incapable of carrying
    per-asset content: the only thing it is given is the project configuration.
    """
    project = spec_store.load_project(root)
    return CompiledBriefing(project=project.name, text=render_project_briefing(project))


__all__ = [
    "COMPILED_FILENAME",
    "CompiledBriefing",
    "CompiledSpec",
    "compile_project_briefing",
    "compile_spec",
]
