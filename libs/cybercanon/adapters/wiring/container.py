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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.credential_store import CredentialStore
from cybercanon.application.ports.document_platform import (
    DEFAULT_BUDGET,
    NO_CREDENTIAL,
    Credential,
    DocumentPlatform,
    NullDocumentPlatform,
)
from cybercanon.application.ports.image_inspector import ImageInspector
from cybercanon.application.ports.interactive_sign_in import InteractiveSignIn
from cybercanon.application.ports.llm import DisabledLLM, LLMPort
from cybercanon.application.ports.mesh_inspector import MeshInspector
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.ports.search_index import RecordedMiss, SearchIndex
from cybercanon.application.ports.spec_store import ProjectConfig, SpecStore
from cybercanon.application.ports.thumbnail_renderer import ThumbnailRenderer
from cybercanon.application.ports.view_index import ViewIndex
from cybercanon.application.ports.vision import DisabledVision, VisionPort
from cybercanon.application.results import Result, Unavailable
from cybercanon.application.use_cases.compile_spec import (
    CompiledBriefing,
    CompiledSpec,
    compile_project_briefing,
    compile_spec,
)
from cybercanon.application.use_cases.derived_metadata import (
    AcceptedAlias,
    Derivation,
    DescribedAsset,
    RejectedSuggestion,
    accept_suggestion,
    describe_view,
    list_derived,
    reject_suggestion,
    suggest_aliases,
)
from cybercanon.application.use_cases.diff_spec import SpecDifference, diff_asset_spec
from cybercanon.application.use_cases.documents import (
    CardCache,
    DocumentListing,
    DocumentWorkspace,
    RecordedLink,
    create_document_for_asset,
    link_document,
    list_document_revisions,
    list_linked_documents,
    unlink_document,
)
from cybercanon.application.use_cases.index_assets import (
    Fingerprinter,
    RebuildReport,
    no_fingerprints,
    rebuild_index,
)
from cybercanon.application.use_cases.ingest_views import (
    IngestionOutcome,
    UploadedImage,
    ingest_views,
    limits_of,
    remove_view,
)
from cybercanon.application.use_cases.lint_spec import (
    LintFinding,
    LintReport,
    lint_actor_mapping,
    lint_project,
    lint_specs,
)
from cybercanon.application.use_cases.lookup_assets import (
    AssetListing,
    LocationAnswer,
    SearchAnswer,
    list_assets,
    nearest_ids,
    recorded_misses,
    search_assets,
    spec_path_for,
    where_is,
)
from cybercanon.application.use_cases.resolve_actor import (
    ActorResolver,
    AuthorSource,
    Resolution,
    Resolver,
    UnmappedAuthors,
    list_unmapped_people,
    no_authors,
)
from cybercanon.application.use_cases.search_delegation import (
    DelegatedSearch,
    search_assets_and_docs,
)
from cybercanon.application.use_cases.sign_in import (
    Announce,
    SignedIn,
    SignedOut,
    SignInStatus,
    announce_nothing,
    sign_in,
    sign_in_status,
    sign_out,
)
from cybercanon.application.use_cases.spec_lens import (
    Lens,
    LensedSpec,
    read_asset_spec,
    read_open_annotations,
)
from cybercanon.application.use_cases.validate_export import ValidationOutcome, validate_export
from cybercanon.application.use_cases.view_mirror import ViewMirrorReport, mirror_views
from cybercanon.application.use_cases.view_revisions import (
    ConceptView,
    list_view_revisions,
)
from cybercanon.domain.actors import GitAuthor
from cybercanon.domain.documents import DocumentHistory, DocumentRef, DocumentScope
from cybercanon.domain.identity import Actor

NO_INDEX = (
    "this container was built without a search index; lookup, search and "
    "specification reads by identifier need one"
)

NO_SIGN_IN = (
    "this container was built with no identity service configured; `canon auth "
    "login` needs CANON_AUTH_ISSUER and CANON_AUTH_CLIENT_ID in the environment"
)

SIGN_IN_UNAVAILABLE = Unavailable(identifier="sign_in.unconfigured", message=NO_SIGN_IN)
"""What a container built with no identity service answers to `canon auth login`.

A refusal rather than a crash, and *unavailable* rather than *invalid*: nothing
the person typed is wrong, and the fix is a configured issuer rather than a
different command.
"""

NO_WORKING_COPY = (
    "this container was built with no working copy, so nothing can be committed "
    "to a repository through it; run `canon` inside a git checkout"
)

WORKING_COPY_UNAVAILABLE = Unavailable(
    identifier="project.no_working_copy", message=NO_WORKING_COPY
)
"""What a container built for validation alone answers to a write.

A returned refusal rather than a raise, exactly as :data:`INDEX_UNAVAILABLE` is:
it reaches an inbound adapter as an outcome like every other, and no surface
needs an `except` to render it.
"""

NO_BLOB_STORE = (
    "this container was built with no blob storage, so there is no mirror to "
    "rebuild; the views themselves are in the repository either way"
)

BLOB_STORE_UNAVAILABLE = Unavailable(identifier="blob.unconfigured", message=NO_BLOB_STORE)
"""What a container with no mirror answers to a re-mirror. Not a failure.

`concept-ingestion` makes the mirror optional by specification — *"with no blob
storage configured at all, ingestion SHALL commit and the view SHALL be readable
from the repository"* — so asking an unmirrored project to re-mirror is a
request that cannot apply rather than one that went wrong.
"""

INDEX_UNAVAILABLE = Unavailable(identifier="index.unavailable", message=NO_INDEX)
"""What a container built for validation alone answers to a lookup (D10).

A returned refusal rather than a raise, because it reaches an inbound adapter
like every other outcome: a pre-commit hook wired with no index and a hosted
surface whose index is still rebuilding get the same vocabulary, and neither
surface needs an `except` to render it.
"""

USE_CASES: tuple[str, ...] = (
    "validate_export",
    "lint_specs",
    "lint_project",
    "compile_spec",
    "compile_project_briefing",
    "where_is",
    "list_assets",
    "search_assets",
    "search_assets_and_docs",
    "nearest_assets",
    "asset_spec",
    "open_annotations",
    "diff_spec",
    "link_document",
    "unlink_document",
    "list_linked_documents",
    "list_document_revisions",
    "create_document_for_asset",
    "describe_views",
    "suggest_aliases",
    "list_derived_metadata",
    "accept_suggested_alias",
    "reject_suggested_alias",
    "rebuild_index",
    "recorded_misses",
    "resolve_actor",
    "lint_actor_mapping",
    "unmapped_authors",
    "sign_in",
    "sign_out",
    "sign_in_status",
)
"""Every use case this change ships, by the name the container resolves it under.

A test walks this tuple, so a use case added without a way to reach it from an
inbound adapter fails the build rather than waiting for someone to notice.
"""


@dataclass(frozen=True)
class Container:
    """The wired application: the ports, and every use case over them.

    `search_index`, `actor_resolver` and `fingerprints` arrive with the read
    surface. They carry defaults so a container built for validation alone —
    the pre-commit path, which must work with no index and no identity — is
    still constructible with the three ports it has always needed.
    """

    spec_store: SpecStore
    mesh_inspector: MeshInspector
    blob_store: BlobStore | None = None
    search_index: SearchIndex | None = None
    actor_resolver: Resolver | None = None
    fingerprints: Fingerprinter = no_fingerprints
    authors: AuthorSource = no_authors
    credential_store: CredentialStore | None = None
    interactive_sign_in: InteractiveSignIn | None = None
    repository_host: RepositoryHost | None = None
    """The working copy this container writes through, when it has one.

    Absent for a container built for validation alone, which reads a checkout
    and writes nothing. Present for `canon` — over the checkout the person is
    standing in — and for the hosted surface, over the volume it fetched.
    Concept ingestion is the first use case in the container that needs it,
    because it is the first one that commits.
    """

    image_inspector: ImageInspector | None = None
    thumbnail_renderer: ThumbnailRenderer | None = None
    view_index: ViewIndex | None = None
    """The three ports concept ingestion brings (add-concept-ingestion D1, D3, D9).

    All optional, and their absence is a local wiring rather than a broken one:
    without a thumbnail renderer nothing is derived, without a view index
    nothing is recorded, and both are rebuildable from the repository by
    specification.
    """

    document_platform: DocumentPlatform = field(default_factory=NullDocumentPlatform)
    """The document platform, which is the null one unless configured (D4).

    A default rather than an optional, and that is the whole of the degradation
    idiom: there is no `None` to check, so no use case can branch on whether
    linked-document features are available, and *"every other capability works"*
    is a property of the wiring instead of fifteen scattered conditionals.
    """

    document_workspace: str = ""
    """The platform workspace a document created from this deployment is made in."""

    document_budget: timedelta = DEFAULT_BUDGET
    """How long one delegated search may take before the answer is *not this time* (D5).

    Configuration rather than a constant, because it is the deployment's
    patience and not the product's: it is `CANON_ARCHE_TIMEOUT_S`, read once at
    composition, and the local half of a search has already finished by the time
    it starts counting.
    """

    card_cache: CardCache = field(default_factory=CardCache)
    """The per-(reference, actor) display cache (D3). Rebuildable; never durable."""

    llm: LLMPort = field(default_factory=DisabledLLM)
    vision: VisionPort = field(default_factory=DisabledVision)
    """The two model ports, which are the disabled ones unless configured.

    Defaults rather than optionals, exactly as `document_platform` is: there is
    no ``None`` to check, so no use case branches on whether a model is
    available, and *"the system SHALL be fully usable with it off"* is a
    property of the wiring rather than of fifteen scattered conditionals.

    Two ports and not one, because the vision identifier is configured
    separately — a deployment with text and no vision is a state this pair can
    hold.
    """

    project_id: str = ""
    """What this container serves its project as, when that is not the declared name.

    Empty on a laptop: `canon` is standing *in* a working copy, and the project
    is whatever `.canon/project.yaml` calls itself. A hosted deployment sets it
    to the address it serves the project at, because `http-api` makes that
    address permanent while the declared name is repository content a commit can
    change — and because every project-keyed decision has to be made with one
    string. Entitlement, the index rows and the working-copy directory then agree
    by construction instead of agreeing whenever the two happen to match.
    """

    # -- validation ------------------------------------------------------

    def validate_export(
        self, export: str, *, emit_preview: bool = False
    ) -> Result[ValidationOutcome]:
        """One export against its governing specification."""
        return validate_export(
            export,
            spec_store=self.spec_store,
            mesh_inspector=self.mesh_inspector,
            blob_store=self.blob_store,
            emit_preview=emit_preview,
        )

    # -- specification files ---------------------------------------------

    def lint_specs(self, paths: Sequence[str]) -> Result[LintReport]:
        """The structural checks over the specification files themselves."""
        return lint_specs(paths, spec_store=self.spec_store)

    def lint_project(self, root: str = "") -> Result[LintReport]:
        """The same checks over every specification at or below `root`."""
        return lint_project(root, spec_store=self.spec_store)

    def lint_actor_mapping(self, root: str = "") -> Result[tuple[LintFinding, ...]]:
        """The structural checks over `.canon/actors.yaml` on their own (D12)."""
        return lint_actor_mapping(root, spec_store=self.spec_store)

    # -- compilation -----------------------------------------------------

    def compile_spec(self, spec_path: str) -> Result[CompiledSpec]:
        """One asset's specification, compiled into its briefing."""
        return compile_spec(spec_path, spec_store=self.spec_store)

    def compile_project_briefing(self, root: str = "") -> Result[CompiledBriefing]:
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

    @property
    def project_name(self) -> str:
        """The project this working copy is, as the index and the entitlement spell it.

        :attr:`project_id` wins when it is set. It is the address a deployment
        serves this working copy at, and an address that stopped meaning the same
        project the moment somebody edited `name:` would be an entitlement that
        changed in a commit.
        """
        return self.project_id or self.project().name or ""

    def over_index[T](self, operation: Callable[[SearchIndex], Result[T]]) -> Result[T]:
        """Run a use case that needs the index, or say this container has none.

        The one branch in this module, and it is about wiring rather than about
        an asset: *was this container built for lookup*. Every method below that
        needs an index goes through it, so "no index" is one sentence in one
        place instead of ten.
        """
        if self.search_index is None:
            return INDEX_UNAVAILABLE
        return operation(self.search_index)

    # -- identity (D4) ---------------------------------------------------

    def resolve_actor(self) -> Resolution:
        """Who is acting: the chain ending in a local, unauthenticated actor.

        It takes no argument, here as in the use case, because there is no
        parameter through which a caller could influence the answer.
        """
        return (self.actor_resolver or ActorResolver(project=self.project_name)).resolve()

    # -- signing in and out (task 8.6) -----------------------------------

    def sign_in(self, announce: Announce = announce_nothing) -> Result[SignedIn]:
        """Approve a device authorization in a browser and keep what it issues.

        Both ports or neither: obtaining a credential and having somewhere to
        put it are one operation, and a container holding only the second would
        report a sign-in it could not perform.
        """
        if self.credential_store is None or self.interactive_sign_in is None:
            return SIGN_IN_UNAVAILABLE
        return sign_in(
            interactive_sign_in=self.interactive_sign_in,
            credential_store=self.credential_store,
            announce=announce,
        )

    def sign_out(self) -> Result[SignedOut]:
        """Remove this machine's stored credential. Twice is not an error."""
        if self.credential_store is None:
            return SIGN_IN_UNAVAILABLE
        return sign_out(credential_store=self.credential_store)

    def sign_in_status(self) -> Result[SignInStatus]:
        """Whether a credential is stored on this machine — never what it is."""
        if self.credential_store is None:
            return SIGN_IN_UNAVAILABLE
        return sign_in_status(credential_store=self.credential_store)

    def unmapped_authors(self, root: str = "") -> Result[UnmappedAuthors]:
        """The project's git authors and recorded owners the mapping does not bind.

        Two sources because a project has two kinds of author: the people in its
        history, which the composition root reads through :attr:`authors`, and
        the people its specification files name as owners. Both are addresses
        that will be rendered as somebody, so both have to be completable.
        """
        return self.over_index(
            lambda index: list_unmapped_people(
                spec_store=self.spec_store,
                search_index=index,
                authors=self.authors(),
                project=self.project_name or None,
                root=root,
            )
        )

    # -- lookup and search -----------------------------------------------

    def where_is(self, asset_id: str) -> Result[LocationAnswer]:
        """Every recorded location of one asset, with the unrecorded ones named."""
        return self.over_index(
            lambda index: where_is(
                asset_id,
                spec_store=self.spec_store,
                search_index=index,
                fingerprints=self.fingerprints,
                project=self.project_name or None,
            )
        )

    def list_assets(
        self,
        *,
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> Result[AssetListing]:
        """The project's assets, narrowed by every filter that was given."""
        return self.over_index(
            lambda index: list_assets(
                spec_store=self.spec_store,
                search_index=index,
                project=self.project_name or None,
                status=status,
                owner=owner,
                tag=tag,
            )
        )

    def search_assets(self, term: str) -> Result[SearchAnswer]:
        """The ranked cascade of D9, with a zero-result term recorded locally."""
        return self.over_index(
            lambda index: search_assets(term, search_index=index, project=self.project_name or None)
        )

    def search_assets_and_docs(
        self,
        term: str,
        *,
        credential: Credential = NO_CREDENTIAL,
    ) -> Result[DelegatedSearch]:
        """The local cascade, plus the delegated half when the gate opens (D5, D7).

        The credential is the **caller's own** and travels as an argument, so no
        surface can delegate a question without having decided whose authority
        it is asking with. With none, the local half still answers and the
        semantic half reports itself unavailable for lack of authority.
        """
        return self.over_index(
            lambda index: search_assets_and_docs(
                term,
                search_index=index,
                platform=self.document_platform,
                credential=credential,
                project=self.project_name or None,
                budget=self.document_budget,
                workspace=self.document_workspace,
            )
        )

    def nearest_assets(self, asset_id: str) -> Result[tuple[str, ...]]:
        """The indexed identifiers closest to one nobody recognised."""
        return self.over_index(
            lambda index: nearest_ids(
                asset_id, search_index=index, project=self.project_name or None
            )
        )

    def recorded_misses(self) -> Result[tuple[RecordedMiss, ...]]:
        """Every search term that matched nothing, with how often it was asked."""
        return self.over_index(
            lambda index: recorded_misses(search_index=index, project=self.project_name or None)
        )

    def rebuild_index(self, root: str = "") -> Result[RebuildReport]:
        """Scan every specification under `root` and rewrite the project's rows."""
        return self.over_index(
            lambda index: rebuild_index(
                root,
                spec_store=self.spec_store,
                search_index=index,
                fingerprints=self.fingerprints,
                project=self.project_id,
            )
        )

    def spec_path_for(self, asset_id: str) -> Result[str]:
        """The specification file one asset is written in, by identifier."""
        return self.over_index(
            lambda index: spec_path_for(
                asset_id,
                spec_store=self.spec_store,
                search_index=index,
                fingerprints=self.fingerprints,
                project=self.project_name or None,
            )
        )

    # -- lensed reads (D2, D3) -------------------------------------------

    def asset_spec(self, asset_id: str, lens: str | Lens | None = None) -> Result[LensedSpec]:
        """One asset's specification as a discipline sees it — authorized first."""
        return self.over_index(
            lambda index: read_asset_spec(
                asset_id,
                lens,
                spec_store=self.spec_store,
                search_index=index,
                resolution=self.resolve_actor(),
                project=self.project_name,
                fingerprints=self.fingerprints,
            )
        )

    def open_annotations(self, asset_id: str) -> Result[LensedSpec]:
        """The threads still open on one asset, and nothing else."""
        return self.over_index(
            lambda index: read_open_annotations(
                asset_id,
                spec_store=self.spec_store,
                search_index=index,
                resolution=self.resolve_actor(),
                project=self.project_name,
                fingerprints=self.fingerprints,
            )
        )

    # -- concept views (add-concept-ingestion) ---------------------------

    def over_working_copy[T](self, operation: Callable[[RepositoryHost], Result[T]]) -> Result[T]:
        """Run a use case that commits, or say this container has no working copy.

        The same shape as :meth:`over_index`, and about wiring rather than about
        an asset: a pre-commit container reads a checkout and writes nothing, so
        "no working copy" is one sentence in one place instead of four.
        """
        if self.repository_host is None:
            return WORKING_COPY_UNAVAILABLE
        return operation(self.repository_host)

    def add_views(
        self,
        asset_id: str,
        uploads: Sequence[UploadedImage],
        *,
        author: GitAuthor | None,
        subject: str = "",
        agent: str = "",
        name: str = "",
    ) -> Result[IngestionOutcome]:
        """Ingest one or more concept views — the same use case every surface calls."""
        return self.over_working_copy(
            lambda host: ingest_views(
                self.project_name,
                asset_id,
                uploads,
                repository_host=host,
                spec_store=self.spec_store,
                image_inspector=self.image_inspector,
                author=author,
                limits=limits_of(self.project()),
                blob_store=self.blob_store,
                thumbnail_renderer=self.thumbnail_renderer,
                view_index=self.view_index,
                subject=subject,
                agent=agent,
                name=name,
            )
        )

    def remove_view(
        self, asset_id: str, slot: str, *, author: GitAuthor | None, subject: str = ""
    ) -> Result[IngestionOutcome]:
        """Remove a view. A removal is a revision, and nothing earlier is lost."""
        return self.over_working_copy(
            lambda host: remove_view(
                self.project_name,
                asset_id,
                slot,
                repository_host=host,
                spec_store=self.spec_store,
                author=author,
                subject=subject,
            )
        )

    def view_revisions(self, asset_id: str, slot: str) -> Result[ConceptView]:
        """One view's revisions, newest first, read from the repository alone."""
        return self.over_working_copy(
            lambda host: list_view_revisions(
                self.project_name,
                asset_id,
                slot,
                repository_host=host,
                spec_store=self.spec_store,
                image_inspector=self.image_inspector,
            )
        )

    def rebuild_view_mirror(self) -> Result[ViewMirrorReport]:
        """Re-mirror every concept view and re-derive its thumbnails (task 3.5).

        The recovery `concept-ingestion` specifies, as an operation somebody can
        run: *"deleting every mirrored object and every thumbnail and rebuilding
        SHALL restore every view"*. It is the same pass ingestion's own
        mirroring step takes — one function, called twice — so the keys it lands
        on are the keys it had.
        """
        if self.blob_store is None:
            return BLOB_STORE_UNAVAILABLE
        return self.over_working_copy(
            lambda host: mirror_views(
                self.project_name,
                repository_host=host,
                spec_store=self.spec_store,
                blob_store=self.blob_store,
                view_index=self.view_index,
                thumbnail_renderer=self.thumbnail_renderer,
            )
        )

    # -- derived metadata (add-derived-metadata) -------------------------

    def derivation_for(
        self,
        asset_id: str,
        *,
        actor: Actor | None = None,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> Derivation | None:
        """Everything one generation or acceptance needs, or ``None`` with no working copy.

        The index is required as well as the repository: derived content lives
        in the index by specification, so a container built for validation alone
        — no index, no checkout — cannot generate and says so rather than
        quietly producing records nowhere.
        """
        if self.repository_host is None or self.search_index is None:
            return None
        return Derivation(
            project=self.project_name,
            asset_id=asset_id,
            repository_host=self.repository_host,
            spec_store=self.spec_store,
            search_index=self.search_index,
            vision=self.vision,
            actor=actor,
            author=author,
            agent=agent,
        )

    def describe_views(
        self,
        asset_id: str,
        *,
        slot: str = "",
        actor: Actor | None = None,
    ) -> Result[DescribedAsset]:
        """Generate a description, tags and suggested aliases for an asset's views."""
        return self.over_derivation(
            asset_id, actor, lambda derivation: describe_view(derivation, slot)
        )

    def suggest_aliases(
        self,
        asset_id: str,
        *,
        slot: str = "",
        actor: Actor | None = None,
    ) -> Result[DescribedAsset]:
        """The alias proposals for an asset — generated if they are not there yet."""
        return self.over_derivation(
            asset_id, actor, lambda derivation: suggest_aliases(derivation, slot)
        )

    def list_derived_metadata(
        self, asset_id: str, *, actor: Actor | None = None
    ) -> Result[DescribedAsset]:
        """What is already derived for this asset. Never calls a model."""
        return self.over_derivation(asset_id, actor, list_derived)

    def accept_suggested_alias(
        self,
        asset_id: str,
        source_hash: str,
        value: str,
        *,
        written: str = "",
        actor: Actor | None = None,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> Result[AcceptedAlias]:
        """Write one accepted alias into `asset.yaml`, attributed to this person."""
        return self.over_derivation(
            asset_id,
            actor,
            lambda derivation: accept_suggestion(derivation, source_hash, value, written),
            author=author,
            agent=agent,
        )

    def reject_suggested_alias(
        self,
        asset_id: str,
        source_hash: str,
        value: str,
        *,
        actor: Actor | None = None,
        author: GitAuthor | None = None,
    ) -> Result[RejectedSuggestion]:
        """Refuse one suggested value for one image, permanently."""
        return self.over_derivation(
            asset_id,
            actor,
            lambda derivation: reject_suggestion(derivation, source_hash, value),
            author=author,
        )

    def over_derivation[T](
        self,
        asset_id: str,
        actor: Actor | None,
        operation: Callable[[Derivation], Result[T]],
        *,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> Result[T]:
        """Run a derived-metadata use case, or say this container cannot.

        The same shape as :meth:`over_index` and :meth:`over_working_copy`, and
        about wiring rather than about an asset.
        """
        derivation = self.derivation_for(asset_id, actor=actor, author=author, agent=agent)
        if derivation is None:
            return WORKING_COPY_UNAVAILABLE
        return operation(derivation)

    # -- history (D10) ---------------------------------------------------

    # -- linked documents (add-cyberarche-integration) -------------------

    def document_workspace_for(
        self,
        asset_id: str,
        *,
        credential: Credential = NO_CREDENTIAL,
        actor: Actor | None = None,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> DocumentWorkspace:
        """Everything one document-link operation needs, assembled once.

        The credential is the **caller's own** and travels as an argument, so
        no surface can reach the platform without having decided whose
        authority it is acting with (D2).
        """
        return DocumentWorkspace(
            project=self.project_name,
            asset_id=asset_id,
            spec_store=self.spec_store,
            repository_host=self.repository_host,
            platform=self.document_platform,
            credential=credential,
            actor=actor,
            author=author,
            agent=agent,
            default_workspace=self.document_workspace,
            cache=self.card_cache,
        )

    def list_linked_documents(
        self,
        asset_id: str,
        *,
        credential: Credential = NO_CREDENTIAL,
        actor: Actor | None = None,
    ) -> Result[DocumentListing]:
        """Every document linked to this asset and to its project, as this viewer sees it."""
        return list_linked_documents(
            self.document_workspace_for(asset_id, credential=credential, actor=actor)
        )

    def list_document_revisions(
        self,
        asset_id: str,
        document_id: str,
        *,
        credential: Credential = NO_CREDENTIAL,
        actor: Actor | None = None,
    ) -> Result[DocumentHistory]:
        """A linked document's own version history, read through the platform."""
        return list_document_revisions(
            self.document_workspace_for(asset_id, credential=credential, actor=actor),
            document_id,
        )

    def link_document(
        self,
        asset_id: str,
        ref: DocumentRef,
        *,
        scope: DocumentScope = DocumentScope.ASSET,
        actor: Actor | None = None,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> Result[RecordedLink]:
        """Record one reference as authored content, attributed to the acting person."""
        return link_document(
            self.document_workspace_for(asset_id, actor=actor, author=author, agent=agent),
            ref,
            scope,
        )

    def unlink_document(
        self,
        asset_id: str,
        document_id: str,
        *,
        scope: DocumentScope = DocumentScope.ASSET,
        actor: Actor | None = None,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> Result[RecordedLink]:
        """Remove one reference. The document at the platform is never touched."""
        return unlink_document(
            self.document_workspace_for(asset_id, actor=actor, author=author, agent=agent),
            document_id,
            scope,
        )

    def create_document_for_asset(
        self,
        asset_id: str,
        title: str = "",
        *,
        credential: Credential = NO_CREDENTIAL,
        actor: Actor | None = None,
        author: GitAuthor | None = None,
        agent: str = "",
    ) -> Result[RecordedLink]:
        """Create an empty pre-titled document for this asset and link it (D8)."""
        return create_document_for_asset(
            self.document_workspace_for(
                asset_id, credential=credential, actor=actor, author=author, agent=agent
            ),
            title,
        )

    def diff_spec(self, asset_id: str, revision: str) -> Result[SpecDifference]:
        """How one asset's specification has moved since a revision."""
        return self.over_index(
            lambda index: diff_asset_spec(
                asset_id,
                revision,
                spec_store=self.spec_store,
                search_index=index,
                fingerprints=self.fingerprints,
                project=self.project_name or None,
            )
        )


__all__ = [
    "INDEX_UNAVAILABLE",
    "NO_INDEX",
    "NO_SIGN_IN",
    "NO_WORKING_COPY",
    "SIGN_IN_UNAVAILABLE",
    "USE_CASES",
    "Container",
]
