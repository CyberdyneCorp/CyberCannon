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
from dataclasses import dataclass

from cybercanon.application.ports.blob_store import BlobStore
from cybercanon.application.ports.credential_store import CredentialStore
from cybercanon.application.ports.interactive_sign_in import InteractiveSignIn
from cybercanon.application.ports.mesh_inspector import MeshInspector
from cybercanon.application.ports.search_index import RecordedMiss, SearchIndex
from cybercanon.application.ports.spec_store import ProjectConfig, SpecStore
from cybercanon.application.results import Result, Unavailable
from cybercanon.application.use_cases.compile_spec import (
    CompiledBriefing,
    CompiledSpec,
    compile_project_briefing,
    compile_spec,
)
from cybercanon.application.use_cases.diff_spec import SpecDifference, diff_asset_spec
from cybercanon.application.use_cases.index_assets import (
    Fingerprinter,
    RebuildReport,
    no_fingerprints,
    rebuild_index,
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
    "nearest_assets",
    "asset_spec",
    "open_annotations",
    "diff_spec",
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
        """The project this working copy is, as the index and the entitlement spell it."""
        return self.project().name or ""

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

    # -- history (D10) ---------------------------------------------------

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
    "SIGN_IN_UNAVAILABLE",
    "USE_CASES",
    "Container",
]
