"""One wired HTTP surface, built from the in-memory fakes and nothing else.

The point of building it here rather than in each test is that every test then
drives the **real application** — the routers, the pipeline, the outcome
mapping, the versioned prefix — against a working copy that exists only in
memory. Nothing on disk, no database, no identity service, and therefore nothing
that makes a surface test slow enough that people stop running it.

The shape mirrors what the composition root will hand in: one
:class:`~cybercanon.adapters.inbound.http.surface.HostedProject` per project,
each carrying the container the command line would have built and the repository
host its reads are pinned against.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from fastapi.testclient import TestClient

from cybercanon.adapters.inbound.http.app import build_app
from cybercanon.adapters.inbound.http.surface import Dependency, HostedProject, Surface
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.testing import build_fakes
from cybercanon.application.testing.idempotency import InMemoryIdempotencyStore
from cybercanon.domain.actors import ActorBinding, ActorMapping
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.identity import Actor, ActorId, ActorKind, Role

PROJECT = "cyberdyne-game"
OTHER_PROJECT = "cyberdyne-art"

SCOUT = "mech_scout"
SCOUT_SPEC = "characters/mech_scout/asset.yaml"
SCOUT_CONTENT = b"id: mech_scout\n"

TOKEN = "rafa-token"
READER_TOKEN = "ana-token"
STRANGER_TOKEN = "stranger-token"
AUTOMATION_TOKEN = "scheduler-token"

RAFA = "auth|rafa"
ANA = "auth|ana"

RAFA_EMAIL = "rafa@cyberdyne.com"
ANA_EMAIL = "ana@cyberdyne.com"


def a_person(
    subject: str = RAFA,
    name: str = "Rafa",
    project: str = PROJECT,
    roles: tuple[Role, ...] = (Role.ART_DIRECTOR,),
) -> Actor:
    return Actor(id=ActorId(subject), display_name=name, roles=roles, projects=(project,))


def automation(project: str = PROJECT) -> Actor:
    """A service credential holding every role — the caller D13 refuses."""
    return Actor(
        id=ActorId("auth|scheduler"),
        display_name="the nightly refresh",
        roles=tuple(Role),
        projects=(project,),
        kind=ActorKind.AUTOMATION,
    )


def an_asset(asset_id: str = SCOUT, owner_art: str | None = None, **constraints: Any) -> Asset:
    return Asset(
        id=AssetId(asset_id),
        name=asset_id.replace("_", " ").title(),
        owner_art=owner_art,
        constraints=Constraints(naming="SM_{asset}_LOD{n}", **constraints),
    )


def an_index_row(asset_id: str, spec_path: str, project: str = PROJECT) -> IndexedAsset:
    return IndexedAsset(
        asset_id=asset_id,
        name=asset_id.replace("_", " ").title(),
        spec_path=spec_path,
        project=project,
    )


@dataclass
class Wired:
    """The application under test, and every fake it was built over."""

    client: TestClient
    surface: Surface
    fakes: Mapping[str, Any]

    @property
    def spec_store(self) -> Any:
        return self.fakes["spec_store"]

    @property
    def search_index(self) -> Any:
        return self.fakes["search_index"]

    @property
    def repository_host(self) -> Any:
        return self.fakes["repository_host"]

    @property
    def identity_provider(self) -> Any:
        return self.fakes["identity_provider"]

    def get(self, path: str, token: str = TOKEN, **arguments: Any) -> Any:
        return self.client.get(path, headers=_headers(token), **arguments)

    def put(self, path: str, token: str = TOKEN, key: str = "", **arguments: Any) -> Any:
        return self.client.put(path, headers=_headers(token, key), **arguments)

    def post(self, path: str, token: str = TOKEN, key: str = "", **arguments: Any) -> Any:
        return self.client.post(path, headers=_headers(token, key), **arguments)

    def patch(self, path: str, token: str = TOKEN, key: str = "", **arguments: Any) -> Any:
        return self.client.patch(path, headers=_headers(token, key), **arguments)

    def delete(self, path: str, token: str = TOKEN, key: str = "", **arguments: Any) -> Any:
        return self.client.request("DELETE", path, headers=_headers(token, key), **arguments)

    @property
    def notifier(self) -> Any:
        return self.fakes["notifier"]

    @property
    def image_inspector(self) -> Any:
        return self.fakes["image_inspector"]

    @property
    def blob_store(self) -> Any:
        return self.fakes["blob_store"]

    @property
    def dismissals(self) -> Any:
        return self.fakes["dismissals"]


def _headers(token: str, key: str = "") -> dict[str, str]:
    """The two headers this surface reads: the credential, and the write's key."""
    bearer = {"Authorization": f"Bearer {token}"} if token else {}
    return bearer | ({"Idempotency-Key": key} if key else {})


class UnreachableIndex:
    """An index that fails in a way the domain never expressed.

    Every attribute is a call that raises a plain :class:`RuntimeError` carrying
    the kind of detail a response must never contain. It stands in for the class
    of failure `http-api` calls *"a reason the domain did not express"*: a driver
    that went away, a bug, anything that is not one of the seven outcomes.
    """

    detail = "could not reach postgresql://canon:hunter2@db.internal:5432/canon"

    def __getattr__(self, name: str) -> Any:
        def fails(*arguments: Any, **keywords: Any) -> Any:
            raise RuntimeError(UnreachableIndex.detail)

        return fails


def with_broken_index(wired: Wired) -> Wired:
    """The same surface, with an index that raises instead of answering."""
    hosted = wired.surface.projects[PROJECT]
    broken = replace(hosted, container=replace(hosted.container, search_index=UnreachableIndex()))
    surface = replace(wired.surface, projects={PROJECT: broken})
    return Wired(client=TestClient(build_app(surface=surface)), surface=surface, fakes=wired.fakes)


def a_surface(
    *,
    assets: Mapping[str, str] | None = None,
    dependencies: tuple[Dependency, ...] = (),
    mapped: bool = True,
    declared: str = "",
    origins: tuple[str, ...] = (),
) -> Wired:
    """A surface serving one project, with the assets a test asked for.

    `mapped` controls whether the acting person has a git identity in
    `.canon/actors.yaml` (D8). Off, every write is refused naming the missing
    entry — which is the behaviour, not a limitation of the fixture.

    `declared` is what the working copy's `.canon/project.yaml` calls itself,
    and it defaults to the address so that the ordinary fixture is the ordinary
    deployment. A test that sets it to something else is asking the question the
    address exists to answer: which of the two names is the project's identity.

    `origins` is the browser origins this deployment permits
    (:mod:`cybercanon.adapters.inbound.http.cors`). Empty means none, which is
    what a service nobody pointed a web application at grants.
    """
    fakes = build_fakes()
    spec_store, index, host = fakes["spec_store"], fakes["search_index"], fakes["repository_host"]
    spec_store.set_project(ProjectConfig(name=declared or PROJECT))
    for asset_id, spec_path in (assets or {SCOUT: SCOUT_SPEC}).items():
        spec_store.add(spec_path, an_asset(asset_id))
        index.upsert(an_index_row(asset_id, spec_path))
    if mapped:
        spec_store.set_actor_mapping(
            ActorMapping(
                bindings=(
                    ActorBinding(subject=RAFA, display_name="Rafa", emails=(RAFA_EMAIL,)),
                    ActorBinding(subject=ANA, display_name="Ana", emails=(ANA_EMAIL,)),
                )
            )
        )
    host.add_project(PROJECT, {SCOUT_SPEC: SCOUT_CONTENT})
    host.clone(PROJECT)
    spec_store.snapshot(host.head(PROJECT).value)

    provider = fakes["identity_provider"]
    provider.add(Credential(TOKEN), a_person())
    provider.add(
        Credential(STRANGER_TOKEN),
        a_person(subject="auth|stranger", name="Sam", project=OTHER_PROJECT),
    )
    provider.add(Credential(READER_TOKEN), a_person(subject=ANA, name="Ana", roles=()))
    provider.add(Credential(AUTOMATION_TOKEN), automation())

    container = Container(
        spec_store=spec_store,
        mesh_inspector=fakes["mesh_inspector"],
        blob_store=fakes["blob_store"],
        search_index=index,
    )
    surface = Surface(
        projects={PROJECT: HostedProject(name=PROJECT, container=container, repository_host=host)},
        identity_provider=provider,
        idempotency=InMemoryIdempotencyStore(),
        dismissals=fakes["dismissals"],
        notifier=fakes["notifier"],
        image_inspector=fakes["image_inspector"],
        thumbnail_renderer=fakes["thumbnail_renderer"],
        view_index=fakes["view_index"],
        observe=lambda: dependencies,
        web_origins=origins,
    )
    return Wired(client=TestClient(build_app(surface=surface)), surface=surface, fakes=fakes)
