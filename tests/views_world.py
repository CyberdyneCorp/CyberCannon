"""What a concept-ingestion test has on the table, shared by the unit suite and the steps.

Its own module at the root of `tests/` rather than a conftest, for the reason
`tests/bdd/world.py` gives: two directories here have conftests of their own, and
a shared name would resolve to whichever pytest inserted first. Everything below
is used by `tests/unit/test_use_case_ingest_views.py`,
`tests/unit/test_use_case_view_revisions.py` and by the two step modules, so
that the scenarios and the unit tests are exercising one arrangement rather than
two that drift.

Three pieces:

* :class:`RepositorySpecStore` — a `SpecStore` that reads its specifications
  **out of the repository host**, at a revision, exactly as `GitSpecStore` reads
  them out of a working copy. The in-memory store cannot be used here: ingestion
  commits an `asset.yaml` and then reads it back, and a store seeded separately
  would answer what a test remembered to put in it rather than what the commit
  actually wrote. It parses with the real reader, so D10's minimal specification
  is genuinely parsed rather than asserted about as text.
* :class:`Views` — the ports one ingestion runs against, with the seams a
  scenario needs: an unreachable mirror, a failing thumbnail step, a second
  writer arriving mid-upload.
* the fixtures and helpers the two suites share, so `an_image` means the same
  bytes in a unit test and in a scenario.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from canon_fixtures import image as fixtures
from cybercanon.adapters.outbound.git import schema, writer, yaml_io
from cybercanon.application.ports.spec_store import (
    PROJECT_CONFIG_PATH,
    HistoryUnavailable,
    LoadedMapping,
    LoadedSpec,
    ProjectConfig,
    SpecDocument,
    SpecNotFound,
    SpecUnreadable,
)
from cybercanon.application.testing.blob_store import InMemoryBlobStore
from cybercanon.application.testing.image_inspector import InMemoryImageInspector
from cybercanon.application.testing.repository_host import InMemoryRepositoryHost
from cybercanon.application.testing.thumbnail_renderer import InMemoryThumbnailRenderer
from cybercanon.application.testing.view_index import InMemoryViewIndex
from cybercanon.application.use_cases.ingest_views import UploadedImage, ingest_views, remove_view
from cybercanon.application.use_cases.view_revisions import (
    compare_view_revisions,
    current_view_token,
    get_view_revision,
    list_view_revisions,
)
from cybercanon.domain.actors import ActorBinding, ActorMapping, GitAuthor
from cybercanon.domain.revisions import ContentHash, Revision
from cybercanon.domain.views import ImageFacts, IngestionLimits

PROJECT = "cyberdyne-game"

SCOUT = "mech_scout"
SCOUT_DIR = f"characters/{SCOUT}"
SCOUT_SPEC = f"{SCOUT_DIR}/asset.yaml"

RAFA = GitAuthor(name="Rafa", email="rafa@cyberdyne.com")
ANA = GitAuthor(name="Ana", email="ana@cyberdyne.com")

RAFA_SUBJECT = "auth|rafa"

SPEC_SUFFIX = "asset.yaml"

MAPPING = ActorMapping(
    bindings=(ActorBinding(subject=RAFA_SUBJECT, display_name="Rafa", emails=(RAFA.email,)),)
)


def a_spec(asset_id: str = SCOUT, name: str = "Scout Mech", status: str = "concept") -> bytes:
    """The smallest `asset.yaml` a test needs — the shape D10 writes."""
    return (f"schema_version: 1\nid: {asset_id}\nname: {name}\nstatus: {status}\n").encode()


# --------------------------------------------------------------------------
# A SpecStore over the repository
# --------------------------------------------------------------------------


@dataclass
class RepositorySpecStore:
    """Specifications read out of the repository host, pinned to a revision.

    This is what `GitSpecStore` is for a hosted deployment, in the smallest form
    that answers the port: a tree listing filtered to `asset.yaml`, parsed with
    the adapter's own reader. Using the real reader matters — ingestion writes a
    specification and something has to read it back, and a test that parsed it
    with its own parser would be checking its parser.
    """

    host: InMemoryRepositoryHost
    project: str = PROJECT
    revision: str | None = None
    mapping: ActorMapping = MAPPING
    config: ProjectConfig = field(default_factory=ProjectConfig)

    def pinned(self, revision: str) -> RepositorySpecStore:
        return RepositorySpecStore(
            host=self.host,
            project=self.project,
            revision=revision,
            mapping=self.mapping,
            config=self.config,
        )

    def current_revision(self) -> str | None:
        return self.revision

    def specs_under(self, start: str) -> tuple[str, ...]:
        prefix = start.strip("/")
        return tuple(
            path
            for path in self.host.paths_at(self.project, self._revision())
            if path.endswith(SPEC_SUFFIX) and (not prefix or path.startswith(f"{prefix}/"))
        )

    def load(self, spec_path: str) -> LoadedSpec:
        content = self.host.read(self.project, spec_path, self._revision())
        if content is None:
            raise SpecNotFound(spec_path)
        return _loaded(spec_path, content)

    def load_at(self, spec_path: str, revision: str) -> LoadedSpec:
        content = self.host.read(self.project, spec_path, Revision(revision))
        if content is None:
            raise HistoryUnavailable(spec_path, revision, "that revision does not hold it")
        return _loaded(spec_path, content)

    def revisions_for(self, spec_path: str, limit: int | None = None) -> tuple[str, ...]:
        history = self.host.history(self.project, spec_path, limit)
        return tuple(entry.revision.value for entry in history.revisions)

    def discover(self, start: str) -> str | None:
        candidate = f"{start.rstrip('/')}/{SPEC_SUFFIX}"
        return candidate if candidate in self.specs_under("") else None

    def load_project(self, start: str) -> ProjectConfig:
        """The configuration, with its document links read out of the repository.

        The static half is whatever a test seeded; the `documents:` half is read
        from `.canon/project.yaml` in the host, because a project-scoped link is
        *written* there and a store that answered a remembered value would make
        a write that landed and a write that did not look identical.
        """
        content = self.host.read(self.project, PROJECT_CONFIG_PATH, self._revision())
        if content is None:
            return self.config
        data = yaml_io.load_mapping(content.decode("utf-8"), subject=PROJECT_CONFIG_PATH)
        parsed, _ = schema.parse_project_file(data)
        documents, _ = schema.to_documents(parsed.documents, "documents")
        return replace(self.config, documents=documents)

    def edited_project(self, content: bytes, documents) -> bytes:
        """The adapter's own writer over `.canon/project.yaml`, comments intact."""
        text = content.decode("utf-8") if content else ""
        return writer.render_project(text, documents).encode("utf-8")

    def load_actor_mapping(self, start: str = "") -> LoadedMapping:
        return LoadedMapping(mapping=self.mapping)

    def read_document(self, spec_path: str, revision: str | None = None) -> SpecDocument:
        """The file as an editable document — the real bytes, through the real reader."""
        at = Revision(revision) if revision else self._revision()
        content = self.host.read(self.project, spec_path, at)
        if content is None:
            raise SpecNotFound(spec_path)
        return self.parse_document(spec_path, content)

    def parse_document(self, spec_path: str, content: bytes) -> SpecDocument:
        loaded = _loaded(spec_path, content)
        return SpecDocument(
            path=spec_path,
            content=content,
            asset=loaded.asset,
            warnings=loaded.warnings,
            revision=self.revision or "",
        )

    def edited(self, document: SpecDocument, asset) -> bytes:
        """The adapter's own comment-preserving writer, so the round trip is real."""
        text = document.content.decode("utf-8")
        return writer.render(text, asset, document.asset).encode("utf-8")

    def _revision(self) -> Revision:
        return Revision(self.revision) if self.revision else self.host.head(self.project)


def _loaded(path: str, content: bytes) -> LoadedSpec:
    """One `asset.yaml`, through the adapter's own reader."""
    try:
        data = yaml_io.load_mapping(content.decode("utf-8"), subject=path)
    except (yaml_io.YamlUnreadable, UnicodeDecodeError) as error:
        raise SpecUnreadable(path, str(error)) from error
    parsed, warnings = schema.parse_asset_file(data)
    asset, more = schema.to_asset(parsed)
    return LoadedSpec(asset=asset, path=path, warnings=(*warnings, *more))


# --------------------------------------------------------------------------
# The world one ingestion runs in
# --------------------------------------------------------------------------


@dataclass
class Views:
    """Every port an ingestion touches, plus the helpers the two suites share."""

    host: InMemoryRepositoryHost
    spec_store: RepositorySpecStore
    inspector: InMemoryImageInspector = field(default_factory=InMemoryImageInspector)
    renderer: InMemoryThumbnailRenderer = field(default_factory=InMemoryThumbnailRenderer)
    blobs: InMemoryBlobStore | None = field(default_factory=InMemoryBlobStore)
    index: InMemoryViewIndex = field(default_factory=InMemoryViewIndex)
    limits: IngestionLimits = field(default_factory=IngestionLimits)
    notes: dict[str, Any] = field(default_factory=dict)

    # -- images ----------------------------------------------------------

    def an_image(
        self,
        image_format: str = "png",
        width: int = 1024,
        height: int = 768,
        *,
        seed: int = 0,
        alpha: bool = False,
        byte_size: int | None = None,
    ) -> bytes:
        """Bytes this world's inspector knows the facts of.

        `byte_size` overrides what the facts report, which is how a test stages
        a 41 MB upload without writing 41 MB — the domain decides over
        `ImageFacts` and never over a file (D1), so the size is a fact like any
        other.
        """
        content = fixtures.image_bytes(
            _encoder(image_format), width, height, seed=seed, alpha=alpha
        )
        self.inspector.add(
            content,
            ImageFacts(
                format=image_format,
                width=width,
                height=height,
                byte_size=len(content) if byte_size is None else byte_size,
                content_hash=ContentHash.of(content),
                has_alpha=alpha,
            ),
        )
        return content

    def unreadable_bytes(self) -> bytes:
        """Bytes that are not an image at all."""
        content = fixtures.not_an_image()
        self.inspector.add_unreadable(content, "it is not a recognised image")
        return content

    # -- operations ------------------------------------------------------

    def ingest(
        self,
        asset_id: str = SCOUT,
        uploads: tuple[UploadedImage, ...] = (),
        *,
        author: GitAuthor | None = RAFA,
        subject: str = RAFA_SUBJECT,
        agent: str = "",
        name: str = "",
    ):
        return ingest_views(
            PROJECT,
            asset_id,
            uploads,
            repository_host=self.host,
            spec_store=self.spec_store,
            image_inspector=self.inspector,
            author=author,
            limits=self.limits,
            blob_store=self.blobs,
            thumbnail_renderer=self.renderer,
            view_index=self.index,
            subject=subject,
            agent=agent,
            name=name,
        )

    def upload(
        self, slot: str = "front", content: bytes | None = None, filename: str = ""
    ) -> UploadedImage:
        return UploadedImage(
            slot=slot,
            content=self.an_image() if content is None else content,
            filename=filename,
        )

    def remove(self, asset_id: str = SCOUT, slot: str = "front", *, author: GitAuthor = RAFA):
        return remove_view(
            PROJECT,
            asset_id,
            slot,
            repository_host=self.host,
            spec_store=self.spec_store,
            author=author,
        )

    def revisions(self, asset_id: str = SCOUT, slot: str = "front"):
        return list_view_revisions(
            PROJECT,
            asset_id,
            slot,
            repository_host=self.host,
            spec_store=self.spec_store,
            image_inspector=self.inspector,
        )

    def retrieve(self, revision: str, asset_id: str = SCOUT, slot: str = "front"):
        return get_view_revision(
            PROJECT,
            asset_id,
            slot,
            revision,
            repository_host=self.host,
            spec_store=self.spec_store,
        )

    def compare(self, first: str, second: str, asset_id: str = SCOUT, slot: str = "front"):
        return compare_view_revisions(
            PROJECT,
            asset_id,
            slot,
            first,
            second,
            repository_host=self.host,
            spec_store=self.spec_store,
            image_inspector=self.inspector,
        )

    def token(self, asset_id: str = SCOUT, slot: str = "front"):
        return current_view_token(
            PROJECT,
            asset_id,
            slot,
            repository_host=self.host,
            spec_store=self.spec_store,
        )

    # -- what landed -----------------------------------------------------

    def files(self) -> dict[str, bytes]:
        """What the branch holds now — what a test asserts actually landed."""
        return self.host.remote_files(PROJECT)

    def commits(self):
        return self.host.commits(PROJECT)

    def stored_keys(self) -> tuple[str, ...]:
        """Every key the mirror holds, so an orphan object is visible."""
        return () if self.blobs is None else self.blobs.keys()


def a_world(files: dict[str, bytes] | None = None, *, mapped: bool = True) -> Views:
    """A cloned project holding whatever a test asked for, and nothing else."""
    host = InMemoryRepositoryHost()
    host.add_project(PROJECT, dict(files or {}))
    host.clone(PROJECT)
    mapping = MAPPING if mapped else ActorMapping()
    return Views(host=host, spec_store=RepositorySpecStore(host=host, mapping=mapping))


def with_asset(status: str = "concept", **files: bytes) -> Views:
    """A project whose `mech_scout` already exists, plus any extra files."""
    return a_world({SCOUT_SPEC: a_spec(status=status), **files})


def _encoder(image_format: str) -> str:
    return {"png": fixtures.PNG, "jpeg": fixtures.JPEG, "webp": fixtures.WEBP}.get(
        image_format, fixtures.TIFF
    )


__all__ = [
    "ANA",
    "MAPPING",
    "PROJECT",
    "RAFA",
    "RAFA_SUBJECT",
    "SCOUT",
    "SCOUT_DIR",
    "SCOUT_SPEC",
    "RepositorySpecStore",
    "Views",
    "a_spec",
    "a_world",
    "with_asset",
]
