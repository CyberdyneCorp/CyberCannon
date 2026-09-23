"""Rendering the compiled briefing — pure text, no I/O, no clock, no identity.

`art-spec.md` is what a contractor, a new hire or a language model reads years
after this tool is replaced, so the rules here are conservative:

* **Rules and open issues only.** Resolved and promoted annotations are excluded
  by construction — the renderer is handed `asset.open_annotations` and has no
  way to reach the rest — so the output cannot grow as the tool is used. A
  promoted annotation's content appears among the *rules*, because promotion
  moved it there; the thread it came from stays in git history where no context
  window pays for it.
* **Effective values, already merged.** The compiler and the validator consume
  the identical `EffectiveSpec` (D3), so the briefing a human reads and the
  contract the validator enforces cannot drift.
* **Every block is attributed to the discipline that authored it**, because the
  output has to be readable with no other document to interpret it.
* **Deterministic.** Fixed section order, fixed field order, no dictionaries
  iterated, no timestamp, no host name, no author of the compilation. Compiling
  the same specification twice is byte-identical, which is what makes the file
  reviewable in a diff.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.domain.annotations import Annotation, marked
from cybercanon.domain.asset import Asset, Links
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.design import State
from cybercanon.domain.effective_spec import EffectiveSpec, RequiredClip

DERIVED_NOTICE = (
    "> Derived file — CyberCanon compiles it from `asset.yaml`. Edit the "
    "specification, not this file.\n"
    "> It carries durable rules and currently open issues only; resolved and "
    "promoted threads live in git history."
)

PROJECT_NOTICE = (
    "> Derived file — CyberCanon compiles it from `.canon/project.yaml`. Edit the "
    "configuration, not this file.\n"
    "> It carries the project's standing rules and shared constraints only; no "
    "asset's concept and no asset's annotations."
)

NOTHING_DECLARED = "_Nothing declared._"


def render_asset_briefing(asset: Asset, spec: EffectiveSpec, source: str | None = None) -> str:
    """The compiled `art-spec.md` for one asset."""
    return _document(
        (
            _heading(asset, source),
            _concept(asset),
            _design(asset, spec),
            _constraints(asset, spec),
            _open_issues(asset),
            _links(asset),
        )
    )


def render_project_briefing(project: ProjectConfig) -> str:
    """The project-wide briefing: shared constraints and golden rules, nothing else."""
    return _document(
        (
            "\n".join(
                (
                    f"# {project.name or 'Project'} — standing rules",
                    "",
                    PROJECT_NOTICE,
                )
            ),
            _golden_rules(project),
            _section(
                "Shared constraints — authored by engineering",
                _default_lines(project.defaults),
                note="Project defaults. An asset's own declaration overrides any of these.",
            ),
        )
    )


# --------------------------------------------------------------------------
# Asset sections
# --------------------------------------------------------------------------


def _heading(asset: Asset, source: str | None) -> str:
    lines = [
        f"# {asset.id.value} — {asset.name}",
        "",
        f"**Status:** {asset.status}",
    ]
    if asset.aliases:
        lines.append(f"**Also known as:** {', '.join(asset.aliases)}")
    if source:
        lines.append(f"**Compiled from:** `{source}`")
    lines.extend(("", DERIVED_NOTICE))
    return "\n".join(lines)


def _concept(asset: Asset) -> str:
    concept = asset.concept
    return _section(
        "Concept — authored by art",
        (
            *_owner(asset.owner_art),
            *_bullets("Silhouette rule", concept.silhouette_rules if concept else ()),
            *_listing("Concept views", concept.views if concept else ()),
        ),
    )


def _design(asset: Asset, spec: EffectiveSpec) -> str:
    design = asset.design
    fields = (
        ("Role", design.role if design else None),
        ("Read distance", _metres(design.read_distance_m if design else None)),
        ("Silhouette priority", design.silhouette_priority if design else None),
        ("Scale reference", design.scale_ref if design else None),
        ("Team colour regions", _joined(design.team_color_regions if design else ())),
    )
    return _section(
        "Design — authored by design",
        (
            *_owner(asset.owner_design),
            *_fields(fields),
            *_sockets(spec),
            *_states(asset, spec),
        ),
    )


def _sockets(spec: EffectiveSpec) -> tuple[str, ...]:
    if not spec.required_sockets:
        return ()
    return (
        "",
        "**Required attachment points** — the export is rejected without them:",
        *(f"- `{name}`" for name in spec.required_sockets),
    )


def _states(asset: Asset, spec: EffectiveSpec) -> tuple[str, ...]:
    states = asset.design.states if asset.design else ()
    if not states:
        return ()
    return ("", "**States:**", *(_state_line(state, spec) for state in states))


def _state_line(state: State, spec: EffectiveSpec) -> str:
    if state.is_unanimated:
        return f"- `{state.name}` — declared unanimated; no clip required."
    required = next((clip for clip in spec.required_clips if clip.state == state.name), None)
    if required is None:
        return (
            f"- `{state.name}` — **resolves to no clip.** Declare a clip, a clip "
            "naming convention, or `animated: false`."
        )
    return f"- `{state.name}` — clip `{required.clip_name}`{_expectations(required)}"


def _expectations(required: RequiredClip) -> str:
    declared = _fragments(
        (
            (f"{required.frame_rate} fps", required.frame_rate is not None),
            (f"at least {required.min_duration_s} s", required.min_duration_s is not None),
            ("root motion", bool(required.root_motion)),
            ("loop closed", bool(required.loop)),
        )
    )
    return f" ({', '.join(declared)})" if declared else ""


def _constraints(asset: Asset, spec: EffectiveSpec) -> str:
    return _section(
        "Engineering constraints — authored by engineering",
        (*_owner(asset.owner_code), *_effective_lines(spec)),
        note=(
            "Effective values: project defaults with the asset's own "
            "declarations taking precedence."
        ),
    )


def _effective_lines(spec: EffectiveSpec) -> tuple[str, ...]:
    rig = spec.rig
    texture = spec.texture
    return _fields(
        (
            ("Triangle budget", spec.tri_budget),
            ("LOD triangle budgets", _joined(tuple(str(count) for count in spec.lods))),
            ("Up axis", spec.up_axis),
            ("Unit scale", spec.unit_scale),
            ("Object naming", _code(spec.naming)),
            ("Pivot", spec.pivot),
            ("Collider", spec.collider),
            ("Texture size", texture.size if texture else None),
            ("Texture sets", texture.sets if texture else None),
            ("Texture channels", _joined(texture.channels if texture else ())),
            ("Skeleton", rig.skeleton if rig else None),
            ("Bone budget", rig.max_bones if rig else None),
            ("Clip naming", _code(spec.clip_naming)),
            ("Clip frame rate", spec.frame_rate),
        )
    )


def _default_lines(defaults: Constraints | None) -> tuple[str, ...]:
    if defaults is None:
        return ()
    rig = defaults.rig
    return _fields(
        (
            ("Triangle budget", defaults.tri_budget),
            ("Up axis", defaults.up_axis),
            ("Unit scale", defaults.unit_scale),
            ("Object naming", _code(defaults.naming)),
            ("Pivot", defaults.pivot),
            ("Collider", defaults.collider),
            ("Bone budget", rig.max_bones if rig else None),
            ("Clip naming", _code(defaults.clip_naming)),
            ("Clip frame rate", defaults.animation.frame_rate if defaults.animation else None),
        )
    )


def _open_issues(asset: Asset) -> str:
    return _section(
        "Open issues",
        tuple(_issue(annotation) for annotation in asset.open_annotations),
        note="Open only. A resolved or promoted thread is not context; it is history.",
    )


def _issue(annotation: Annotation) -> str:
    """One open issue, naming who said it and — when it matters — what they are.

    `mcp-write-surface` requires agent authorship to be visible *"wherever an
    annotation is presented to a person"*, the compiled briefing included, and
    visible *"without the reader inspecting anything further"*. The attribution
    (`rafa, via blender-agent`) and the marking both come from the domain, so
    the briefing, the agent surface and the web application cannot end up
    describing one annotation three ways. An unanchored observation is marked
    here too, beside the target it named: a reader who cannot tell that a thread
    no longer lands anywhere will act on it as though it does.
    """
    return (
        f"- **[{annotation.kind}]** on `{annotation.durable_key}` "
        f"({annotation.attribution}){marked(annotation)}: {annotation.text}"
    )


def _links(asset: Asset) -> str:
    """The Links section — addresses exactly as authored, and never a title.

    A linked long-form document appears here as **its bare reference**: the
    address the specification holds, with nothing resolved from the document
    platform. That is what makes *"the two outputs SHALL be byte-identical"*
    true whether the platform is reachable or not — there is no line here that
    could differ, because nothing in this function has anything to ask.

    Compilation contacts nothing, and it could not: this is a pure function of
    the asset and the merged specification, with no port in its signature.
    """
    links = asset.links
    if links is None and not asset.documents:
        return ""
    declared = links or Links()
    return _section(
        "Links",
        (
            *_fields(
                (
                    ("Source file", _code(declared.source)),
                    ("Engine path", _code(declared.engine)),
                    ("Design document", declared.design_doc),
                    ("Discussion", declared.discussion),
                )
            ),
            *_documents(asset),
        ),
    )


def _documents(asset: Asset) -> tuple[str, ...]:
    """One line per linked document: its address, and nothing else it might say."""
    return tuple(f"- **Linked document**: {ref.url}" for ref in asset.documents)


def _golden_rules(project: ProjectConfig) -> str:
    return _section(
        "Golden rules",
        tuple(f"- {rule}" for rule in project.golden_rules),
        note="They apply to every asset in the project.",
    )


# --------------------------------------------------------------------------
# Formatting primitives
# --------------------------------------------------------------------------


def _document(blocks: Sequence[str]) -> str:
    """Blocks joined by one blank line, ending in exactly one newline."""
    return "\n\n".join(block for block in blocks if block) + "\n"


def _section(heading: str, lines: Sequence[str], note: str | None = None) -> str:
    """One `##` section. A section with nothing to say says so, rather than vanishing."""
    prelude = [f"## {heading}", ""]
    if note:
        prelude.extend((f"_{note}_", ""))
    body = tuple(lines) if any(line.strip() for line in lines) else (NOTHING_DECLARED,)
    return "\n".join((*prelude, *body))


def _fields(fields: Iterable[tuple[str, object]]) -> tuple[str, ...]:
    return tuple(
        f"- **{label}**: {value}" for label, value in fields if value is not None and value != ""
    )


def _bullets(label: str, values: Sequence[str]) -> tuple[str, ...]:
    return tuple(f"- **{label}**: {value}" for value in values)


def _listing(label: str, values: Sequence[str]) -> tuple[str, ...]:
    return (f"- **{label}**: {_joined(values)}",) if values else ()


def _owner(owner: str | None) -> tuple[str, ...]:
    return (f"- **Owner**: {owner}",) if owner else ()


def _fragments(candidates: Iterable[tuple[str, bool]]) -> tuple[str, ...]:
    return tuple(text for text, declared in candidates if declared)


def _joined(values: Sequence[str]) -> str:
    return ", ".join(values)


def _metres(value: float | None) -> str | None:
    return None if value is None else f"{value} m"


def _code(value: str | None) -> str | None:
    return None if value is None else f"`{value}`"


__all__ = [
    "DERIVED_NOTICE",
    "NOTHING_DECLARED",
    "PROJECT_NOTICE",
    "render_asset_briefing",
    "render_project_briefing",
]
