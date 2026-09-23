"""Writing an edited specification back — the artist's comments survive it (D4).

This is the half of the file format that only exists once something other than a
person edits `asset.yaml`, and it is the risk `add-model-sheet-2d` names as most
likely to lose a team's trust in one afternoon: *"comment-preserving round trip
damages a hand-authored `asset.yaml`"*. So the rule here is narrow and
mechanical.

* **Only what changed is written.** The edited asset is compared with the one
  that was read, block by block, and a block that did not change is not touched
  at all. An edit that only adds an annotation cannot rewrite the constraints,
  because nothing in this module looks at them on that path.
* **An accepted alias is one term appended to one sequence.**
  `add-derived-metadata`'s D7 asks for a writer that mutates *only the target
  sequence*, and :func:`_set_aliases` mutates the node the document already has
  rather than replacing it — so the file a person wrote comes back with one more
  entry in the list they wrote, in the style they wrote it in, and with no
  marker anywhere saying a model proposed it.
* **An unchanged annotation keeps its own node.** The annotation list is rebuilt
  from the document's existing entries wherever the domain value is unchanged,
  so a comment somebody wrote beside a thread survives a reply to a different
  thread.
* **`ruamel` owns the file and this module owns nothing else.** Loading and
  dumping are :mod:`~cybercanon.adapters.outbound.git.yaml_io`'s, whose round
  trip is asserted byte-for-byte; the only thing here is which keys to set.

Nothing about a *rule* lives here. What a promotion writes is
:mod:`cybercanon.domain.triage`'s decision; this renders the asset that decision
produced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields as dataclass_fields
from typing import Any

from cybercanon.adapters.outbound.git import yaml_io
from cybercanon.domain.annotations import Anchor2D, Anchor3D, Annotation, Camera, Reply, Stroke
from cybercanon.domain.asset import Asset
from cybercanon.domain.concept import Concept
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.documents import DocumentRef

ALIASES = "aliases"
ANNOTATIONS = "annotations"
CONCEPT = "concept"
CONSTRAINTS = "constraints"
DOCUMENTS = "documents"
SILHOUETTE_RULES = "silhouette_rules"


def render(text: str, asset: Asset, previous: Asset) -> str:
    """`text` with this asset's edits applied, and every other line untouched.

    `previous` is what the document currently means, which is how *"only what
    changed is written"* is decided rather than assumed: a caller that passed
    the same asset twice gets its input back.
    """
    document = yaml_io.load(text)
    if document is None:
        document = {}
    if asset.aliases != previous.aliases:
        _set_aliases(document, asset.aliases)
    if asset.annotations != previous.annotations:
        _set_annotations(document, asset.annotations)
    if asset.concept != previous.concept:
        _set_concept(document, asset.concept, previous.concept)
    if asset.constraints != previous.constraints:
        _set_constraints(document, asset.constraints, previous.constraints)
    if asset.documents != previous.documents:
        set_documents(document, asset.documents)
    return yaml_io.dump(document)


def render_project(text: str, documents: Sequence[DocumentRef]) -> str:
    """`.canon/project.yaml` with its `documents:` list replaced, nothing else touched.

    The project configuration is a hand-authored file like `asset.yaml` — golden
    rules, defaults, severities — so a link added to it goes through the same
    comment-preserving round trip, and the only key this function can reach is
    the one it names.
    """
    document = yaml_io.load(text)
    if document is None:
        document = {}
    set_documents(document, documents)
    return yaml_io.dump(document)


def set_documents(document: Any, documents: Sequence[DocumentRef]) -> None:
    """Replace the `documents:` list — references and their authorship, nothing else.

    There is no branch here that could write a title or a summary, because
    :func:`_document` has no line that reads one: *"a title or summary resolved
    from the document platform SHALL NOT be written into a specification
    file"* is a property of this function rather than a rule somebody remembers.
    Its own name is public because `.canon/project.yaml` carries the same block
    for project-scoped links and must write it the same way.
    """
    if not documents:
        document.pop(DOCUMENTS, None)
        return
    document[DOCUMENTS] = [_document(ref) for ref in documents]


def _document(ref: DocumentRef) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "workspace": ref.workspace,
        "id": ref.document_id,
        "url": ref.url,
    }
    _put(entry, "linked_by", ref.linked_by)
    _put(entry, "linked_at", ref.linked_at)
    return entry


# --------------------------------------------------------------------------
# Aliases — the one thing acceptance writes (add-derived-metadata, D7)
# --------------------------------------------------------------------------


def _set_aliases(document: Any, aliases: Sequence[str]) -> None:
    """Bring the `aliases:` sequence to exactly these values, in place.

    **Mutated rather than replaced** whenever the document already has one, and
    that is the whole of the surgical half of D7: a list the artist wrote in
    flow style (`aliases: [mech, walker]`) stays in flow style, its node keeps
    its position among the keys, and a comment beside it survives — so the
    difference an acceptance produces is the one added term and nothing else.
    Assigning a fresh Python list would re-render the sequence in block style
    and turn a one-word change into a rewritten block.

    A document with no `aliases:` at all gains one, which is an added key rather
    than a rewritten file — still *only the intended change*.
    """
    wanted = list(aliases)
    existing = document.get(ALIASES)
    if not isinstance(existing, list):
        if wanted:
            document[ALIASES] = wanted
        else:
            document.pop(ALIASES, None)
        return
    for value in wanted:
        if value not in existing:
            existing.append(value)
    for value in [held for held in existing if held not in wanted]:
        existing.remove(value)
    if not existing:
        document.pop(ALIASES, None)


# --------------------------------------------------------------------------
# Annotations
# --------------------------------------------------------------------------


def _set_annotations(document: Any, annotations: Sequence[Annotation]) -> None:
    """Replace the list, keeping the node of every entry that did not change."""
    if not annotations:
        document.pop(ANNOTATIONS, None)
        return
    existing = _by_id(document.get(ANNOTATIONS) or ())
    document[ANNOTATIONS] = [
        existing[annotation.id]
        if _matches(existing.get(annotation.id), annotation)
        else _annotation(annotation)
        for annotation in annotations
    ]


def _by_id(entries: Sequence[Any]) -> dict[str, Any]:
    """The document's annotation nodes, by the identifier each declares."""
    found: dict[str, Any] = {}
    for entry in entries:
        identifier = entry.get("id") if isinstance(entry, Mapping) else None
        if isinstance(identifier, str):
            found[identifier] = entry
    return found


def _matches(node: Any, annotation: Annotation) -> bool:
    """Whether the document's node already says exactly this.

    Compared by rendering rather than by field, so a member added to
    :class:`~cybercanon.domain.annotations.Annotation` cannot quietly fall out
    of the comparison and leave an edit unwritten.
    """
    return node is not None and _plain(node) == _annotation(annotation)


def _plain(node: Any) -> Any:
    """A round-trip node as plain data, so it compares with rendered output."""
    if isinstance(node, Mapping):
        return {key: _plain(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(entry) for entry in node]
    return node


def _annotation(annotation: Annotation) -> dict[str, Any]:
    """One annotation as the file writes it, in the order a reader reads it."""
    entry: dict[str, Any] = {
        "id": annotation.id,
        "kind": str(annotation.kind),
        "author": annotation.author,
    }
    _put(entry, "via", annotation.via)
    entry["text"] = annotation.text
    entry["state"] = str(annotation.state)
    if annotation.is_agent_authored:
        entry["author_kind"] = str(annotation.author_kind)
    _put(entry, "observation_kind", _observation_kind(annotation))
    _put(entry, "authored_against", annotation.authored_against)
    _put(entry, "created_at", annotation.created_at)
    _put(entry, "edited_at", annotation.edited_at)
    _put(entry, "reanchored_by", annotation.reanchored_by)
    _put(entry, "reanchored_at", annotation.reanchored_at)
    _put(entry, "moved_by", annotation.moved_by)
    _put(entry, "moved_at", annotation.moved_at)
    _put(entry, "closed_by", annotation.closed_by)
    _put(entry, "closed_at", annotation.closed_at)
    _put(entry, "closing_text", annotation.closing_text)
    entry["target"] = _anchor(annotation)
    _put(entry, "replies", [_reply(reply) for reply in annotation.replies])
    _put(entry, "strokes", [_stroke(stroke) for stroke in annotation.strokes])
    return entry


def _observation_kind(annotation: Annotation) -> str:
    """What an agent found, as the file writes it — absent for a person's words."""
    return str(annotation.observation_kind) if annotation.observation_kind else ""


def _put(entry: dict[str, Any], key: str, value: Any) -> None:
    """Write a member only when it carries something.

    An empty optional is absent rather than `''`, so the file a person opens
    holds what somebody meant and not the schema's own defaults.
    """
    if value:
        entry[key] = value


def _reply(reply: Reply) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": reply.id, "author": reply.author}
    _put(entry, "via", reply.via)
    entry["text"] = reply.text
    _put(entry, "at", reply.at)
    _put(entry, "edited_at", reply.edited_at)
    return entry


def _stroke(stroke: Stroke) -> Any:
    """One mark as ordered `[u, v]` pairs — never a raster, never a width (D8)."""
    return yaml_io.inline([yaml_io.inline([u, v]) for u, v in stroke.points])


def _anchor(annotation: Annotation) -> dict[str, Any]:
    """The anchor, in the one shape the schema reads both forms out of."""
    target = annotation.target
    if isinstance(target, Anchor2D):
        return {"view": target.view, "u": target.u, "v": target.v}
    return _part_anchor(target)


def _part_anchor(target: Anchor3D) -> dict[str, Any]:
    entry: dict[str, Any] = {"part": target.part}
    _put(entry, "bone", target.bone)
    _put(entry, "point", list(target.point) if target.point else None)
    _put(entry, "normal", list(target.normal) if target.normal else None)
    _put(entry, "camera", _camera(target.camera))
    _put(entry, "clip", target.clip)
    if target.t is not None:
        # Not through `_put`: a hint at the very start of a clip is `0.0`, and
        # `_put`'s truthiness test would drop exactly that one position.
        entry["t"] = target.t
    return entry


def _camera(camera: Camera | None) -> dict[str, Any] | None:
    if camera is None:
        return None
    return {
        "position": list(camera.position),
        "target": list(camera.target),
        "fov_deg": camera.fov_deg,
    }


# --------------------------------------------------------------------------
# The two promotion destinations
# --------------------------------------------------------------------------


def _set_concept(document: Any, concept: Concept | None, previous: Concept | None) -> None:
    """Write the concept members a promotion can change, and no others."""
    if concept is None:
        return
    block = _block(document, CONCEPT)
    before = previous or Concept()
    if concept.silhouette_rules != before.silhouette_rules:
        block[SILHOUETTE_RULES] = list(concept.silhouette_rules)
    if concept.views != before.views:
        block["views"] = list(concept.views)


def _set_constraints(
    document: Any, constraints: Constraints | None, previous: Constraints | None
) -> None:
    """Write the constraint fields that changed, nested block included."""
    if constraints is None:
        return
    block = _block(document, CONSTRAINTS)
    before = previous or Constraints()
    for field in dataclass_fields(Constraints):
        value = getattr(constraints, field.name)
        if value == getattr(before, field.name):
            continue
        _set_field(block, field.name, value, getattr(before, field.name))


def _set_field(block: Any, name: str, value: Any, before: Any) -> None:
    """One constraint member — a scalar, a list, or a nested block of its own."""
    if value is None:
        block.pop(name, None)
    elif isinstance(value, tuple):
        block[name] = list(value)
    elif hasattr(value, "__dataclass_fields__"):
        _set_nested(_block(block, name), value, before)
    else:
        block[name] = value


def _set_nested(block: Any, value: Any, before: Any) -> None:
    """A `texture`, `rig` or `animation` block, member by changed member."""
    for field in dataclass_fields(type(value)):
        current = getattr(value, field.name)
        if before is not None and current == getattr(before, field.name):
            continue
        _set_field(block, field.name, current, None)


def _block(document: Any, key: str) -> Any:
    """The named mapping, created empty when the document has none."""
    existing = document.get(key)
    if not isinstance(existing, Mapping):
        document[key] = {}
    return document[key]


__all__ = ["render", "render_project", "set_documents"]
