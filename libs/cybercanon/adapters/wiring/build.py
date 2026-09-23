"""Building the real container: the one place an outbound adapter is named (D11).

:mod:`cybercanon.adapters.wiring.container` holds ports; this module chooses the
implementations. The split is structural, not stylistic — an inbound adapter
imports the container type, and if that type's module reached an outbound
adapter the CLI would acquire an import of `trimesh` through the layering
contract D10 forbids. So every concrete class in this change is named exactly
once, below.

**One container, both inbound surfaces (task 6.4).** `canon` and the FastMCP
server are built from the same call, so there is no second place a use case
could be assembled differently: the agent's `validate_export` and the artist's
`canon validate` reach the identical object graph, and a test resolves every use
case in :data:`~cybercanon.adapters.wiring.container.USE_CASES` through both.

Nothing here decides anything about an asset. It reads the project
configuration to learn what preview emission should aim for — a configuration
value, per D7 — and hands the adapters to the container, plus the two callables
the core deliberately refuses to grow a port for: the file fingerprint the
staleness rule compares (D8) and the commit authors the unmapped-author list
works through (D12).

**The working copy this container writes through is a
:class:`~cybercanon.adapters.outbound.git.local_host.LocalRepositoryHost`, not
the hosted one.** `canon` does not own the checkout and never pushes it: the
artist cloned it and the artist decides when her work leaves her machine. The
*use case* above it is the hosted surface's, unchanged, which is what makes
`canon add-view` and the ingestion endpoint produce the same commit.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from cybercanon.adapters.outbound.arche.config import ArcheSettings, settings_from
from cybercanon.adapters.outbound.arche.platform import ArcheDocumentPlatform
from cybercanon.adapters.outbound.auth.discovery import IssuerEndpoints
from cybercanon.adapters.outbound.auth.flows import DeviceAuthorization, Endpoints
from cybercanon.adapters.outbound.auth.keychain import KeychainCredentialStore
from cybercanon.adapters.outbound.fs.blob_store import FsBlobStore
from cybercanon.adapters.outbound.fs.outbox import FileOutbox
from cybercanon.adapters.outbound.git import revisions
from cybercanon.adapters.outbound.git.annotation_writer import GitAnnotationWriter
from cybercanon.adapters.outbound.git.local_host import LocalRepositoryHost
from cybercanon.adapters.outbound.git.spec_store import GitSpecStore
from cybercanon.adapters.outbound.image.inspector import PillowImageInspector
from cybercanon.adapters.outbound.image.thumbnails import PillowThumbnailRenderer
from cybercanon.adapters.outbound.mesh.gltf_preview import PreviewSettings
from cybercanon.adapters.outbound.mesh.trimesh_inspector import TrimeshInspector
from cybercanon.adapters.outbound.openai_compatible.config import ModelSettings
from cybercanon.adapters.outbound.openai_compatible.config import (
    settings_from as model_settings_from,
)
from cybercanon.adapters.outbound.openai_compatible.models import OpenAICompatibleModels
from cybercanon.adapters.outbound.sqlite.search_index import SqliteSearchIndex
from cybercanon.adapters.wiring.configuration import client_ids, group_roles
from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.credential_store import CredentialStore
from cybercanon.application.ports.document_platform import (
    DocumentPlatform,
    NullDocumentPlatform,
)
from cybercanon.application.ports.identity_provider import Credential, IdentityProvider
from cybercanon.application.ports.llm import DisabledLLM, LLMPort
from cybercanon.application.ports.search_index import FileFingerprint
from cybercanon.application.ports.spec_store import PreviewDefaults
from cybercanon.application.ports.vision import DisabledVision, VisionPort
from cybercanon.application.use_cases.index_assets import Fingerprinter
from cybercanon.application.use_cases.observations import ExportDigest
from cybercanon.application.use_cases.resolve_actor import ActorResolver, AuthorSource
from cybercanon.domain.identity import AgentId
from cybercanon.domain.revisions import ContentHash

CANON_DIR = ".canon"
"""Derived blobs live beside the configuration, inside the repository."""

ISSUER = "CANON_AUTH_ISSUER"
CLIENT_ID = "CANON_AUTH_CLIENT_ID"
ORGANISATION = "CANON_AUTH_ORG_ID"
SERVICE_CLIENTS = "CANON_AUTH_SERVICE_CLIENTS"
AUDIENCE = "CANON_AUTH_AUDIENCE"
DEVICE_CODE_URL = "CANON_AUTH_DEVICE_CODE_URL"
TOKEN_URL = "CANON_AUTH_TOKEN_URL"
KEY_SET_URL = "CANON_AUTH_KEY_SET_URL"
GROUP_ROLES = "CANON_AUTH_GROUP_ROLES"

AGENT = "CANON_AGENT"
"""Who is at the other end of the agent server, from its launch configuration (D4).

*"The agent's identifier SHALL come from the launch configuration of the
process, never from a tool parameter or the text of the write."* An agent client
sets it beside the command it spawns; it is a name rather than a secret, which
is why the configuration can hold it and can hold no credential.

A process started without it keeps every read and is refused both writes, which
is the specified behaviour rather than a wiring accident: the container's
`agent` stays ``None`` and the use case refuses naming the missing identifier.
"""


def build_container(root: str | Path, environment: Mapping[str, str] | None = None) -> Container:
    """The container an inbound adapter runs against, over a working copy.

    `root` is any path inside the repository — the working directory a person
    ran `canon` in is the ordinary case, and the directory an agent client was
    pointed at is the other. The spec store resolves the repository root from
    it, and every other adapter is anchored to that same root, so two surfaces
    run against the same files whichever directory they started in.

    No credential is *required* here, and that is the specified behaviour rather
    than an omission: the resolver's chain ends in a local unauthenticated actor
    (D4), so every read works with no identity, no network and no services.
    `canon auth login` is how a person puts one in the machine's credential
    store, and nothing but a write asks for it — which is why the store is
    wired unconditionally (it needs no configuration and opens nothing until it
    is used) while the sign-in flow, and the verifier the stored credential is
    resolved through, are wired only when an issuer is configured.

    **The write destination is chosen here and nowhere else (D1).** The
    annotation writer is this working copy — the one the person is standing in,
    modified and never committed — and the outcome reporter is the local outbox
    under `.canon/`. The hosted surface binds the same two ports to its own
    implementations, and no tool, use case or inbound adapter ever learns which
    of the two it is talking to.
    """
    source = os.environ if environment is None else environment
    spec_store = GitSpecStore(root)
    project = spec_store.load_project("")
    settings = preview_settings(project.preview)
    credential_store = KeychainCredentialStore()
    return Container(
        spec_store=spec_store,
        mesh_inspector=TrimeshInspector(root=spec_store.root, settings=settings),
        blob_store=FsBlobStore(spec_store.root / CANON_DIR),
        search_index=SqliteSearchIndex(spec_store.root),
        actor_resolver=writing_resolver(project.name or "", credential_store, source),
        fingerprints=file_fingerprints(spec_store.root),
        authors=commit_authors(spec_store.root),
        credential_store=credential_store,
        interactive_sign_in=device_sign_in(environment),
        repository_host=LocalRepositoryHost(spec_store.root, project.name or ""),
        image_inspector=PillowImageInspector(),
        thumbnail_renderer=PillowThumbnailRenderer(),
        document_platform=document_platform(environment),
        document_workspace=arche_settings(environment).default_workspace,
        document_budget=arche_settings(environment).timeout,
        llm=language_model(environment),
        vision=vision_model(environment),
        annotation_writer=GitAnnotationWriter(spec_store, root=spec_store.root),
        outcome_reporter=FileOutbox(spec_store.root),
        agent=agent_identifier(source),
        export_digests=export_digests(spec_store.root),
    )


def agent_identifier(source: Mapping[str, str]) -> AgentId | None:
    """The agent this server was launched for, or ``None`` when it was launched for none.

    ``None`` is the state the specification names — *"a server started without
    an agent identifier ... SHALL be refused naming the missing agent
    identifier, and reads SHALL continue to succeed"* — so an absent variable
    produces a container that reads and refuses to write, never one that invents
    an anonymous author.
    """
    declared = source.get(AGENT, "").strip()
    return AgentId(declared) if declared else None


def export_digests(root: Path) -> ExportDigest:
    """What an export's bytes hash to, for D7's outcome identity.

    :meth:`~cybercanon.domain.revisions.ContentHash.of` is the same digest the
    validation worker takes of the same bytes, so a report made from a laptop
    and a record written by the worker identify the same export the same way. A
    file that is not there hashes to nothing: reporting is telemetry, and an
    invented digest would make a re-export look like a retry.
    """

    def digest(export: str) -> str:
        path = root / export
        if not path.is_file():
            return ""
        return ContentHash.of(path.read_bytes()).value

    return digest


def writing_resolver(
    project: str, credential_store: CredentialStore, source: Mapping[str, str]
) -> ActorResolver:
    """Who this machine acts as: the stored credential when there is one (D5).

    The chain is unchanged — configured credential, cached actor, then the local
    unauthenticated actor — and so is the property that matters most: **nothing
    here is required for a read.** With no issuer configured the provider is
    absent, the first link declines, and `canon validate` never learns that a
    credential store exists.

    The credential is read only when an issuer *is* configured, because loading
    it opens the machine's keychain and a validator that touched a locked
    keychain would fail for a reason that has nothing to do with the asset it
    was asked about. An unreachable store is not a failure either: it declines,
    and the write that needed it is refused naming the sign-in action.
    """
    provider = identity_provider(source, project=project)
    if provider is None:
        return ActorResolver(project=project)
    return ActorResolver(project=project, provider=provider, credential=stored(credential_store))


def stored(credential_store: CredentialStore) -> Credential | None:
    """This machine's credential, or ``None`` when it has none it can reach."""
    try:
        return credential_store.load()
    except Exception:  # a locked store is a machine that is not signed in
        return None


def identity_provider(source: Mapping[str, str], project: str = "") -> IdentityProvider | None:
    """The verifier for this machine's own credential, when an issuer is configured.

    ``None`` when the three values it needs are not all there, which is the
    ordinary local case: `canon` is useful on a machine that has never heard of
    an identity service, and writes are then refused with the sign-in action
    rather than the tool refusing to start.

    The other three — the client id, the organisation and the project — are what
    a CyberdyneAuth credential has to be read *against*: the client id says which
    entries of the one `roles` claim are this product's, and the organisation
    plus the project say whether this person may read what this machine is
    standing in. A machine configured with an issuer and none of them verifies
    credentials and entitles nobody, which is the fail-closed direction and is
    visible as a refusal naming what is missing rather than as a silent grant.

    `CANON_AUTH_SERVICE_CLIENTS` is read here for the same reason the hosted
    service reads it: a `type: service` credential says there is no person
    behind it and never says whose machine it is, so the clients whose
    background work this deployment admits are a list somebody wrote down.
    Unset means the empty list, which admits none — the same fail-closed
    direction as the two above, and the refusal names the variable.

    The import is deferred for the reason the keychain's is: verification pulls
    in a JOSE implementation, and a pre-commit `canon validate` should not pay
    for a library it will never call.
    """
    issuer = source.get(ISSUER, "").strip().rstrip("/")
    audience = source.get(AUDIENCE, "").strip()
    key_set_url = source.get(KEY_SET_URL, "").strip()
    if not issuer or not audience or not key_set_url:
        return None
    from cybercanon.adapters.outbound.auth.cyberdyne import CyberdyneAuth, Trust
    from cybercanon.adapters.outbound.auth.keys import CachedKeySet, JwksKeySource

    return CyberdyneAuth(
        trust=Trust(
            issuer=issuer,
            audience=audience,
            client_id=source.get(CLIENT_ID, "").strip(),
            organisation=source.get(ORGANISATION, "").strip(),
            service_clients=_service_clients(source.get(SERVICE_CLIENTS, "")),
        ),
        keys=CachedKeySet(JwksKeySource(key_set_url)),
        project=project,
        group_roles=dict(group_roles(source.get(GROUP_ROLES, ""))),
    )


def _service_clients(declared: str) -> tuple[str, ...]:
    """Whose background work this machine admits. Nothing, unless it was told."""
    listed = declared.strip()
    return client_ids(listed) if listed else ()


def arche_settings(environment: Mapping[str, str] | None = None) -> ArcheSettings:
    """What this deployment was told about the document platform, if anything."""
    return settings_from(environment)


def document_platform(environment: Mapping[str, str] | None = None) -> DocumentPlatform:
    """CyberArche when it is configured, and the null adapter whenever it is not (D4).

    The *whole* of the degradation decision, taken once, here. Incomplete
    configuration — the switch on with no address, or an address with no
    workspace — selects the null adapter too: half a configuration that made
    requests would fail once per page view instead of behaving like the absence
    it is. Nothing above this line ever asks whether the platform is
    configured.
    """
    settings = arche_settings(environment)
    if not settings.is_complete:
        return NullDocumentPlatform()
    return ArcheDocumentPlatform(settings=settings)


def model_settings(environment: Mapping[str, str] | None = None) -> ModelSettings:
    """What this machine was told about a model, if anything. Off by default."""
    return model_settings_from(environment)


def language_model(environment: Mapping[str, str] | None = None) -> LLMPort:
    """The configured endpoint, or the disabled port whenever it is not configured.

    The whole degradation decision for text, taken once, here. Incomplete
    configuration — the switch on with no address, or an address with no model
    identifier — selects the disabled port too: half a configuration that made
    requests would fail once per command instead of behaving like the absence it
    is. Nothing above this line ever asks whether a model is configured.
    """
    settings = model_settings(environment)
    if not settings.is_complete:
        return DisabledLLM()
    return OpenAICompatibleModels(settings=settings)


def vision_model(environment: Mapping[str, str] | None = None) -> VisionPort:
    """The same, for image description, which needs one more identifier.

    Separately decided, because `CANON_LLM_VISION_MODEL` is separately
    configured: a deployment with a text model and no vision model gets a
    working :class:`LLMPort` beside a disabled :class:`VisionPort`, which is the
    state two ports exist to make representable.
    """
    settings = model_settings(environment)
    if not settings.vision_is_complete:
        return DisabledVision()
    return OpenAICompatibleModels(settings=settings)


def device_sign_in(environment: Mapping[str, str] | None = None) -> DeviceAuthorization | None:
    """The terminal sign-in flow, when an issuer and a client are configured.

    ``None`` when either is absent, and the container turns that into a refusal
    naming the two variables. That is the honest shape for a local-first tool:
    `canon` is useful on a machine that has never heard of an identity service,
    so an unconfigured issuer is a command that is unavailable rather than an
    application that will not start — which is the opposite of the hosted
    service's rule, and deliberately so.

    **The endpoints come from the issuer's discovery document, not from a path
    this module knows.** They used to be `<issuer>/oauth/token` and
    `<issuer>/oauth/device/code`, and CyberdyneAuth serves neither: it publishes
    `/api/v1/auth/oauth2/token`, so every terminal sign-in posted its redemption
    into a 404. Replacing one constant with another would have fixed this issuer
    and left the defect standing for the next one, so
    :class:`~cybercanon.adapters.outbound.auth.discovery.IssuerEndpoints` asks
    the issuer instead — on first use, never here, because `canon` builds this
    container on every invocation and a validator must not open a socket.

    `CANON_AUTH_TOKEN_URL` and `CANON_AUTH_DEVICE_CODE_URL` still win where they
    are set, per endpoint, for the deployment whose issuer publishes no document.
    They are the escape hatch now rather than the default, which is the whole of
    the inversion.
    """
    source = os.environ if environment is None else environment
    issuer = source.get(ISSUER, "").strip().rstrip("/")
    client_id = source.get(CLIENT_ID, "").strip()
    if not issuer or not client_id:
        return None
    return DeviceAuthorization(
        endpoints=IssuerEndpoints(
            issuer,
            overrides=Endpoints(
                token=source.get(TOKEN_URL, "").strip(),
                device_authorization=source.get(DEVICE_CODE_URL, "").strip(),
            ),
        ),
        client_id=client_id,
        audience=source.get(AUDIENCE, "").strip(),
    )


def file_fingerprints(root: Path) -> Fingerprinter:
    """What a specification file looks like right now, by `os.stat` (D8).

    Injected rather than reached for, because the core does no file-system work:
    the staleness comparison is the use case's, and the two numbers it compares
    are this function's.
    """

    def fingerprints(path: str) -> FileFingerprint | None:
        absolute = root / path
        if not absolute.is_file():
            return None
        stat = absolute.stat()
        return FileFingerprint(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns)

    return fingerprints


def commit_authors(root: Path) -> AuthorSource:
    """Who has committed to this repository, for the unmapped-author list (D12)."""

    def authors() -> tuple[str, ...]:
        return revisions.authors(root)

    return authors


def preview_settings(declared: PreviewDefaults | None) -> PreviewSettings:
    """The project's decimation settings, falling back to the emitter's own."""
    if declared is None:
        return PreviewSettings()
    default = PreviewSettings()
    return PreviewSettings(
        ratio=declared.ratio if declared.ratio is not None else default.ratio,
        ceiling=declared.ceiling if declared.ceiling is not None else default.ceiling,
    )


__all__ = [
    "AGENT",
    "AUDIENCE",
    "CANON_DIR",
    "CLIENT_ID",
    "DEVICE_CODE_URL",
    "GROUP_ROLES",
    "ISSUER",
    "KEY_SET_URL",
    "ORGANISATION",
    "TOKEN_URL",
    "agent_identifier",
    "arche_settings",
    "build_container",
    "commit_authors",
    "device_sign_in",
    "document_platform",
    "export_digests",
    "file_fingerprints",
    "identity_provider",
    "language_model",
    "model_settings",
    "preview_settings",
    "stored",
    "vision_model",
    "writing_resolver",
]
