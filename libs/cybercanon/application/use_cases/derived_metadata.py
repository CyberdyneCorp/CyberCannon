"""Generating proposals, and the one human act that turns one into canon.

Four use cases and one rule that shapes all of them: **nothing here writes
generated content anywhere a person reads as authoritative.** Descriptions, tags
and suggested aliases go into the rebuildable index keyed by the content hash of
the image they came from; the only thing that ever reaches an `asset.yaml` is a
value a named person accepted, and it arrives there as an ordinary alias with no
marker of where it came from.

* :func:`describe_view` — a description, tags and suggested aliases for an
  asset's concept views. Reuses the record an unchanged image already has and
  makes **no model call** when it does (D5).
* :func:`suggest_aliases` — the same generation, presented as the pending
  proposals a person is asked to decide about.
* :func:`accept_suggestion` — the bridge. One commit, authored by the accepting
  person, adding one alias and touching nothing else.
* :func:`reject_suggestion` — the other exit. Recorded against
  `(source hash, value)`, so the term does not come back for that image.

Five properties are decisions rather than mechanics, and each is a sentence of
the specification:

* **Generation is never implicit.** Nothing in this module is called by a read,
  a listing, a search, a validation or a compilation; the call sites are a
  person's command and a maintenance operation.
* **Unavailability is an outcome, not a failure.** A disabled, misconfigured,
  unreachable, refused, timed-out or unreadable model produces an `Ok` carrying
  the reason, because *"the larger operation SHALL complete"* and a refusal
  would make the surrounding command fail over a feature that is optional by
  construction.
* **Images only.** An asset with a mesh and no concept view is told there is no
  describable source. Nothing here renders anything, and there is no parameter a
  mesh could arrive through.
* **Acceptance is a person's act**, decided by
  :mod:`cybercanon.domain.policy`, which refuses every automated caller for
  every role it might hold.
* **Generated text is normalised and filtered in the domain**, after the model
  answers, so *"existing aliases are not re-suggested"* is arithmetic rather
  than a politely worded prompt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.llm import (
    ModelAnswer,
    ModelUnavailable,
    Unavailability,
    answered,
    unavailable,
)
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.ports.spec_store import SpecDocument, SpecStore
from cybercanon.application.ports.vision import VisionPort
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.hosted_repository import (
    AuthorUnmapped,
    Edit,
    edit_message,
    write_back,
)
from cybercanon.application.use_cases.ingest_views import locate_asset
from cybercanon.application.use_cases.prompts import DESCRIBE_IMAGE, SUGGEST_ALIASES
from cybercanon.application.use_cases.requests import discipline_owners
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.asset import Asset
from cybercanon.domain.derived import (
    NO_DESCRIBABLE_SOURCE,
    DerivedRecord,
    Generation,
    Provenance,
    Suggestion,
    SuggestionState,
    accepted_decision,
    decided,
    excluded_terms,
    normalise,
    normalised_aliases,
    parse_aliases,
    rejected_decision,
)
from cybercanon.domain.identity import Actor, ActorId, AgentId
from cybercanon.domain.policy import REQUIRES_PERSON, Operation, Subject, decide
from cybercanon.domain.revisions import ContentHash, Revision
from cybercanon.domain.views import CONCEPT_DIR, slot_of

COMMIT_SUMMARY = "alias accepted"
"""What the commit message says an acceptance did. Never that a model proposed it.

The commit is the person's, because the value is the person's: they took
responsibility for it. `metadata-acceptance` requires the file to carry no
marker of model origin, and a commit message saying *"accepted a generated
alias"* would put in the history exactly what the file is forbidden to carry.
"""


# --------------------------------------------------------------------------
# Failures — each means something different to the caller
# --------------------------------------------------------------------------


class AssetNotFound(OperationFailed):
    """No specification in this project declares that asset."""

    kind = FailureKind.NOT_FOUND
    identifier = "asset.not_found"

    def __init__(self, project: str, asset_id: str) -> None:
        super().__init__(f"no asset {asset_id!r} is declared in project {project!r}", asset_id)


class NoDescribableSource(OperationFailed):
    """This asset has no concept view, and a mesh is not described (D:images only)."""

    kind = FailureKind.NOT_FOUND
    identifier = "derived.no_describable_source"

    def __init__(self, asset_id: str) -> None:
        super().__init__(f"{asset_id}: {NO_DESCRIBABLE_SOURCE}", asset_id)


class SuggestionNotFound(OperationFailed):
    """Nothing was suggested for that image, or not that value.

    A named failure rather than a silent success, because *"a person accepts a
    suggestion"* has to mean a suggestion that was actually made: a value
    arriving from a stale page is a term nobody proposed, and writing it would
    make acceptance a free-text field with extra steps.
    """

    kind = FailureKind.NOT_FOUND
    identifier = "suggestion.not_found"

    def __init__(self, source_hash: str, value: str) -> None:
        super().__init__(
            f"no pending suggestion {value!r} is recorded for image {source_hash[:12]}",
            value,
        )


class AcceptanceRefused(OperationFailed):
    """The caller may not turn this proposal into authored content."""

    identifier = "suggestion.acceptance_refused"

    def __init__(self, subject: str, reason: str, kind: FailureKind) -> None:
        super().__init__(reason, subject)
        self.kind = kind  # type: ignore[misc]


class UnusableValue(OperationFailed):
    """The value cannot be an alias — empty, or nothing survives normalisation."""

    kind = FailureKind.INVALID
    identifier = "suggestion.unusable_value"

    def __init__(self, value: str) -> None:
        super().__init__(
            f"{value!r} cannot be written as an alias: an alias is lowercase letters, "
            "digits, underscores and hyphens",
            value,
        )


NO_PERSON = "acceptance is a person's act and there is no identified person here"
"""Why acceptance with no resolvable actor is refused (`metadata-acceptance`)."""


# --------------------------------------------------------------------------
# What one generation runs against
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ViewSource:
    """One concept view as bytes, and the address the record is keyed by."""

    path: str
    slot: str
    content: bytes

    @property
    def source_hash(self) -> str:
        """The content hash of the image. The derived record's key, and its only key."""
        return ContentHash.of(self.content).value


@dataclass
class Derivation:
    """Every port one generation or acceptance touches, in one argument.

    A workspace object for the reason `annotations.Workspace` is one: six ports
    and four identity values as positional arguments is a signature nobody reads
    twice the same way, and every use case below needs the same set.
    """

    project: str
    asset_id: str
    repository_host: RepositoryHost
    spec_store: SpecStore
    search_index: SearchIndex
    vision: VisionPort
    actor: Actor | None = None
    author: GitAuthor | None = None
    via: AgentId | None = None
    agent: str = ""
    clock: Clock = system_clock

    @property
    def subject_id(self) -> str:
        return self.actor.subject if self.actor is not None else ""


@dataclass(frozen=True)
class Loaded:
    """The asset this operation acts on: its path, its bytes, and its views."""

    path: str
    document: SpecDocument
    revision: Revision
    views: tuple[ViewSource, ...] = ()

    @property
    def asset(self) -> Asset:
        return self.document.asset

    @property
    def based_on(self) -> ContentHash:
        return ContentHash.of(self.document.content)


@dataclass(frozen=True)
class DescribedAsset:
    """What generation produced for one asset, or the reason it produced nothing.

    `unavailable` present and `generations` empty is the ordinary state of a
    deployment with no model configured, and it is an **`Ok`**: the command ran,
    the asset is fine, and the feature is absent. A refusal here would make
    every surrounding operation fail over something optional by construction.
    """

    project: str
    asset_id: str
    path: str
    generations: tuple[Generation, ...] = ()
    unavailable: ModelUnavailable | None = None

    @property
    def is_available(self) -> bool:
        return self.unavailable is None

    @property
    def reason(self) -> str:
        """Why there is nothing, in the words a person can act on."""
        return self.unavailable.message if self.unavailable is not None else ""

    @property
    def records(self) -> tuple[DerivedRecord, ...]:
        return tuple(generation.record for generation in self.generations)

    @property
    def suggestions(self) -> tuple[Suggestion, ...]:
        return tuple(entry for generation in self.generations for entry in generation.suggestions)

    @property
    def pending(self) -> tuple[str, ...]:
        """Every value still waiting for a person, deduplicated, in order."""
        return tuple(dict.fromkeys(entry.value for entry in self.suggestions if entry.is_pending))

    @property
    def model_calls_made(self) -> bool:
        return any(not generation.reused for generation in self.generations)


@dataclass(frozen=True)
class AcceptedAlias:
    """One suggestion that is now authored content, and the commit that made it so."""

    project: str
    asset_id: str
    path: str
    value: str
    written: str
    actor: str
    revision: str
    committed: bool = True
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RejectedSuggestion:
    """One suggestion a person refused, for one image, permanently."""

    project: str
    asset_id: str
    source_hash: str
    value: str
    actor: str


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


@as_result
def describe_view(derivation: Derivation, slot: str = "") -> DescribedAsset:
    """A description, tags and suggested aliases for this asset's concept views.

    `slot` narrows it to one view; empty means every view the asset holds. An
    image whose derived record is already there is **reused and no model is
    called** (D5), which is what makes a repeated run over a whole project cost
    nothing and makes regeneration idempotent.
    """
    loaded = _load(derivation, slot)
    if not loaded.views:
        raise NoDescribableSource(derivation.asset_id)
    generations: list[Generation] = []
    for view in loaded.views:
        held = derivation.search_index.derived(view.source_hash, derivation.project)
        if held is not None:
            generations.append(_generation(derivation, held, reused=True))
            continue
        produced = _generate(derivation, loaded, view)
        if isinstance(produced, ModelUnavailable):
            return _unavailable(derivation, loaded, tuple(generations), produced)
        generations.append(produced)
    return DescribedAsset(
        project=derivation.project,
        asset_id=derivation.asset_id,
        path=loaded.path,
        generations=tuple(generations),
    )


@as_result
def suggest_aliases(derivation: Derivation, slot: str = "") -> DescribedAsset:
    """The alias proposals for this asset — generated if they are not there yet.

    The same operation as :func:`describe_view` seen from the angle the feature
    exists for. It is deliberately the same use case underneath: two generation
    paths would be two prompts, two records and two answers to *"has this image
    been described"*.
    """
    return describe_view.raising(derivation, slot)


def _generate(
    derivation: Derivation, loaded: Loaded, view: ViewSource
) -> Generation | ModelUnavailable:
    """One image, two questions, one record — or the reason there is no record."""
    described = derivation.vision.describe(view.content, DESCRIBE_IMAGE)
    if not answered(described):
        return described
    listed = derivation.vision.describe(view.content, SUGGEST_ALIASES)
    if not answered(listed):
        return listed
    terms = parse_aliases(listed.text)
    if terms is None:
        return _malformed(listed)
    record = DerivedRecord(
        provenance=Provenance(
            model=listed.model,
            generated_at=derivation.clock(),
            source_hash=view.source_hash,
        ),
        asset_id=derivation.asset_id,
        source_path=view.path,
        description=described.text.strip(),
        tags=normalised_aliases(terms, limit=len(terms)),
        suggested_aliases=normalised_aliases(terms, excluding=_declared(loaded.asset)),
    )
    derivation.search_index.put_derived(record, derivation.project)
    return _generation(derivation, record, reused=False)


MALFORMED_ANSWER = "the model's answer could not be read as a list of terms"
"""What a response that cannot be parsed is reported as. Never partly accepted."""


def _malformed(answer: ModelAnswer) -> ModelUnavailable:
    """An answer that is not a list of terms is refused whole, never in part (D10).

    `answer` is taken and not read, which is the point: there is no branch here
    that could salvage the half of a response that happened to parse, because a
    half-parsed alias list is the one outcome worse than no list — it is the one
    somebody accepts.
    """
    return unavailable(Unavailability.MALFORMED, MALFORMED_ANSWER)


def _generation(derivation: Derivation, record: DerivedRecord, *, reused: bool) -> Generation:
    """One record with every decision anybody has taken about it attached."""
    taken = derivation.search_index.decisions(record.source_hash, derivation.project)
    return Generation(record=record, reused=reused, suggestions=decided(record, taken))


def _unavailable(
    derivation: Derivation,
    loaded: Loaded,
    generations: tuple[Generation, ...],
    reason: ModelUnavailable,
) -> DescribedAsset:
    """Whatever was already there, plus the reason there is no more of it."""
    return DescribedAsset(
        project=derivation.project,
        asset_id=derivation.asset_id,
        path=loaded.path,
        generations=generations,
        unavailable=reason,
    )


def _declared(asset: Asset) -> frozenset[str]:
    """What a suggestion may never repeat: the id, the name and every alias."""
    return excluded_terms(asset.id.value, asset.name, asset.aliases)


# --------------------------------------------------------------------------
# Reading what is already there — never generating
# --------------------------------------------------------------------------


@as_result
def list_derived(derivation: Derivation) -> DescribedAsset:
    """Every derived record this asset already has. **No model is ever called.**

    The read half, and the reason it is a separate use case: `derived-metadata`
    requires that reading, listing, searching, validating and compiling never
    trigger a model call, and a `describe` that quietly generated when it found
    nothing would make that requirement depend on which argument somebody
    passed.
    """
    loaded = _load(derivation, "")
    held = derivation.search_index.derived_records(derivation.project, derivation.asset_id)
    return DescribedAsset(
        project=derivation.project,
        asset_id=derivation.asset_id,
        path=loaded.path,
        generations=tuple(_generation(derivation, record, reused=True) for record in held),
    )


# --------------------------------------------------------------------------
# Acceptance — the bridge from proposal to canon
# --------------------------------------------------------------------------


@as_result
def accept_suggestion(
    derivation: Derivation, source_hash: str, value: str, written: str = ""
) -> AcceptedAlias:
    """Write one accepted alias into `asset.yaml`, as one attributed commit.

    `written` is the person's edit of the proposal, which
    `metadata-acceptance` requires to be possible — *"a person SHALL be able to
    ... edit a value before accepting it"* — and which is attributed to them
    exactly as an unedited acceptance is, because it is even more theirs.

    The file that comes back carries **no marker**: the alias is a normal alias,
    because it is the person's value now. Who accepted what, and when, is the
    index's record (D8); which commit put it there is git's.
    """
    person = _person(derivation)
    loaded = _load(derivation, "")
    _permitted(derivation, loaded)
    record = _recorded(derivation, source_hash)
    term = _accepted_term(derivation, record, value, written)
    asset, changed = _with_alias(loaded.asset, term)
    outcome = _commit(derivation, loaded, asset) if changed else None
    derivation.search_index.record_decision(
        accepted_decision(source_hash, value, person, derivation.clock(), term),
        derivation.project,
    )
    return AcceptedAlias(
        project=derivation.project,
        asset_id=derivation.asset_id,
        path=loaded.path,
        value=value,
        written=term,
        actor=person,
        revision=outcome if outcome is not None else loaded.revision.value,
        committed=changed,
        aliases=asset.aliases,
    )


@as_result
def reject_suggestion(derivation: Derivation, source_hash: str, value: str) -> RejectedSuggestion:
    """Refuse one suggested value for one image, permanently (D6).

    No file changes and no commit is made: a rejection is a fact about a
    proposal, and proposals live in the index. It is keyed by
    `(source hash, value)` so that regenerating from the same unchanged image
    produces the same suggestions and the rejection still applies — which is
    what the specification asks for and what keying on the asset would undo.
    """
    person = _person(derivation)
    record = _recorded(derivation, source_hash)
    if value not in record.suggested_aliases:
        raise SuggestionNotFound(source_hash, value)
    derivation.search_index.record_decision(
        rejected_decision(source_hash, value, person, derivation.clock()),
        derivation.project,
    )
    return RejectedSuggestion(
        project=derivation.project,
        asset_id=derivation.asset_id,
        source_hash=source_hash,
        value=value,
        actor=person,
    )


def _person(derivation: Derivation) -> str:
    """Who is doing this — refusing when there is nobody, and for automation.

    Two refusals, and they are different sentences. *"Acceptance is attempted
    with no resolvable person"* is a caller that never identified itself;
    an automated caller is one that identified itself as not being a person, and
    `project.md` reserves this operation to people for every role it might hold.
    """
    actor = derivation.actor
    if actor is None:
        raise AcceptanceRefused(derivation.asset_id, NO_PERSON, FailureKind.UNAUTHENTICATED)
    if actor.is_automation or derivation.via is not None:
        raise AcceptanceRefused(
            derivation.asset_id,
            f"{actor.display} may not decide a suggestion: it {REQUIRES_PERSON}",
            FailureKind.FORBIDDEN,
        )
    return actor.subject


def _permitted(derivation: Derivation, loaded: Loaded) -> None:
    """G4's row for accepting a suggested alias, decided in the domain and nowhere else."""
    decision = decide(
        derivation.actor,
        Operation.ACCEPT_SUGGESTED_ALIAS,
        Subject(
            project=derivation.project,
            discipline_owner=_art_owner(derivation, loaded),
            has_git_identity=derivation.author is not None,
            description=derivation.asset_id,
        ),
        via=derivation.via,
    )
    if decision.refused:
        raise AcceptanceRefused(derivation.asset_id, decision.reason, FailureKind.FORBIDDEN)


def _art_owner(derivation: Derivation, loaded: Loaded) -> ActorId | None:
    """Who owns the discipline a concept view belongs to — art, resolved to an actor."""
    mapping = derivation.spec_store.load_actor_mapping(loaded.path).mapping
    return discipline_owners(loaded.asset, mapping).art


def _recorded(derivation: Derivation, source_hash: str) -> DerivedRecord:
    """The derived record for that image, or a refusal naming what is missing."""
    record = derivation.search_index.derived(source_hash, derivation.project)
    if record is None:
        raise SuggestionNotFound(source_hash, "")
    return record


def _accepted_term(derivation: Derivation, record: DerivedRecord, value: str, written: str) -> str:
    """The alias that will be written: the proposal, or the person's edit of it."""
    taken = derivation.search_index.decisions(record.source_hash, derivation.project)
    states = {entry.value: entry.state for entry in decided(record, taken)}
    if states.get(value) not in (SuggestionState.PENDING, SuggestionState.ACCEPTED):
        raise SuggestionNotFound(record.source_hash, value)
    term = normalise(written or value)
    if not term:
        raise UnusableValue(written or value)
    return term


def _with_alias(asset: Asset, term: str) -> tuple[Asset, bool]:
    """The asset carrying this alias, and whether anything actually changed.

    Accepting a value the specification already declares writes nothing at all,
    so a retried acceptance is quiet rather than a second identical commit — the
    same discipline the annotation writer uses.
    """
    if term in asset.aliases:
        return asset, False
    return replace(asset, aliases=(*asset.aliases, term)), True


def _commit(derivation: Derivation, loaded: Loaded, asset: Asset) -> str:
    """One logical edit as one attributed commit, with D5's per-file precondition."""
    if derivation.author is None:
        raise AuthorUnmapped(derivation.subject_id, loaded.path)
    content = derivation.spec_store.edited(loaded.document, asset)
    written = write_back.raising(
        derivation.project,
        [Edit(path=loaded.path, content=content, based_on=loaded.based_on)],
        repository_host=derivation.repository_host,
        author=derivation.author,
        message=edit_message(derivation.asset_id, COMMIT_SUMMARY),
        subject=derivation.subject_id,
        agent=derivation.agent,
    )
    return written.revision.value


# --------------------------------------------------------------------------
# Loading — the asset, and the images it holds
# --------------------------------------------------------------------------


def _load(derivation: Derivation, slot: str) -> Loaded:
    """Where this asset is, what its file holds, and which images it has.

    The bytes come from the repository host at the head revision and the meaning
    from the spec store's parse of exactly those bytes — one content, one
    parser, so *what is there now* has a single answer.
    """
    revision = derivation.repository_host.head(derivation.project)
    path = locate_asset(derivation.asset_id, spec_store=derivation.spec_store, revision=revision)
    if path is None:
        raise AssetNotFound(derivation.project, derivation.asset_id)
    content = derivation.repository_host.read(derivation.project, path, revision)
    if content is None:
        raise AssetNotFound(derivation.project, derivation.asset_id)
    return Loaded(
        path=path,
        document=derivation.spec_store.parse_document(path, content),
        revision=revision,
        views=_views(derivation, path, revision, slot),
    )


def _views(
    derivation: Derivation, path: str, revision: Revision, slot: str
) -> tuple[ViewSource, ...]:
    """Every concept image this asset holds, as bytes, in slot order.

    Read from the repository rather than from an index, for the reason
    `locate_asset` is: this has to work on a laptop with no index at all. Only
    files under the asset's `concept/` directory are considered, so a mesh, an
    export or a preview cannot arrive here — *"generation targets images only"*
    is a property of this walk rather than a check somebody remembers.
    """
    prefix = f"{_directory(path)}/{CONCEPT_DIR}/" if _directory(path) else f"{CONCEPT_DIR}/"
    wanted = slot.strip()
    found: list[ViewSource] = []
    for candidate in sorted(derivation.repository_host.paths_at(derivation.project, revision)):
        named = slot_of(candidate)
        if named is None or not candidate.startswith(prefix):
            continue
        if wanted and str(named) != wanted:
            continue
        content = derivation.repository_host.read(derivation.project, candidate, revision)
        if content:
            found.append(ViewSource(path=candidate, slot=str(named), content=content))
    return tuple(found)


def _directory(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def presented(records: Sequence[DerivedRecord]) -> tuple[str, ...]:
    """Every derived record's provenance line, for a surface that lists them.

    `derived-metadata` requires the model identifier, the generation time and
    the source content hash to be available *wherever the derived content is
    presented*, and requires the content to be identified as generated. Both are
    one string, built in one place, so no surface can present half of it.
    """
    return tuple(record.provenance.described for record in records)


__all__ = [
    "COMMIT_SUMMARY",
    "MALFORMED_ANSWER",
    "NO_PERSON",
    "AcceptanceRefused",
    "AcceptedAlias",
    "AssetNotFound",
    "Derivation",
    "DescribedAsset",
    "Loaded",
    "NoDescribableSource",
    "RejectedSuggestion",
    "SuggestionNotFound",
    "UnusableValue",
    "ViewSource",
    "accept_suggestion",
    "describe_view",
    "list_derived",
    "presented",
    "reject_suggestion",
    "suggest_aliases",
]
