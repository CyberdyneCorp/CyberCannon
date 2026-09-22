"""The declared deployment, read as data and checked against the specification.

`deployment-operations` makes three claims about the *set* of deployed things,
and all three are claims a person can only keep by accident unless something
reads them:

* *"the hosted deployment SHALL consist of exactly four components"* — so the
  component set is enumerated from :data:`~canon_deploy.inventory.MANIFEST_PATH`
  and compared with :data:`COMPONENTS`, in both directions;
* *"no other component SHALL be added to the hosted inventory without a
  specification change"* — so a fifth application, or an application whose
  component is one of the two :data:`NEVER_HOSTED` ones, is reported as
  non-conforming and names this specification rather than a preference;
* *"the `canon` command line and the agent server SHALL NOT be deployed as
  network-reachable services, in any environment"* — so both are named in the
  manifest with the reason they are absent, and giving either a host is the
  failure above.

Everything else here is D1's *"four places to keep environment lists honest"*
being paid for once: the variables each application is given are compared with
the settings the service declares, the two health paths with the two the
service serves, and the stop grace period with the drain window D7 makes the
mechanism. A manifest that drifted from the code would be the deployment
document failure one layer down — believed, and wrong.

Nothing here talks to Coolify. The platform is configured from this file by
hand; what the check buys is that the declaration and the code cannot drift in
silence, and that it stays answerable from a checkout on the day the platform
is what is broken.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

MANIFEST_PATH = Path("deploy/coolify.yaml")
"""Where the four applications are declared. Committed, like the ledger."""

HTTP_API = "http_api"
WEB_APPLICATION = "web_application"
INDEX_DATABASE = "index_database"
BLOB_STORE = "blob_store"

COMPONENTS: tuple[str, ...] = (HTTP_API, WEB_APPLICATION, INDEX_DATABASE, BLOB_STORE)
"""The hosted inventory, entire. The specification names these four and no more."""

COMMAND_LINE = "command_line"
AGENT_SERVER = "agent_server"

NEVER_HOSTED: tuple[str, ...] = (COMMAND_LINE, AGENT_SERVER)
"""The two surfaces that are never network-reachable, in any environment."""

REACHABLE: tuple[str, ...] = (HTTP_API, WEB_APPLICATION)
"""The components reachable under the studio's host convention."""

LIVENESS = "/healthz"
READINESS = "/readyz"
DRAIN_WINDOW = "CANON_DRAIN_WINDOW_S"
MIGRATE = "python -m cybercanon.api.migrate"

WORKTREES = "/data/worktrees"
"""The one piece of state the API application owns (D6)."""

SPECIFICATION = "openspec/changes/add-coolify-deployment/specs/deployment-operations/spec.md"


@dataclass(frozen=True)
class Volume:
    """One piece of persistent state, and where the container sees it."""

    name: str
    path: str


@dataclass(frozen=True)
class Health:
    """How the platform decides to restart, to route, and how long to drain."""

    liveness: str = ""
    readiness: str = ""
    stop_grace_period: str = ""


@dataclass(frozen=True)
class Application:
    """One Coolify application: what it is, where it is, what it is given."""

    name: str
    component: str
    host: str = ""
    dockerfile: str = ""
    managed: str = ""
    command: str = ""
    pre_deploy: str = ""
    health: Health = field(default_factory=Health)
    volumes: tuple[Volume, ...] = ()
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    values: Mapping[str, str] = field(default_factory=dict)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(volume.path for volume in self.volumes)


@dataclass(frozen=True)
class Inventory:
    """Everything the deployment declares, hosted and deliberately not."""

    instance: str = ""
    host_suffix: str = ""
    applications: tuple[Application, ...] = ()
    never_hosted: Mapping[str, str] = field(default_factory=dict)

    @property
    def components(self) -> tuple[str, ...]:
        """What is deployed, by the specification's own vocabulary."""
        return tuple(one.component for one in self.applications)

    def by_component(self, component: str) -> Application | None:
        for one in self.applications:
            if one.component == component:
                return one
        return None


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def load(path: Path) -> Inventory:
    """The manifest, as values. A malformed one raises rather than half-loads."""
    document = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    declared = document.get("applications") or {}
    return Inventory(
        instance=str(document.get("instance", "")),
        host_suffix=str(document.get("host_suffix", "")),
        applications=tuple(_application(name, body) for name, body in declared.items()),
        never_hosted={
            name: str((body or {}).get("why", "")).strip()
            for name, body in (document.get("never_hosted") or {}).items()
        },
    )


def _application(name: str, body: Mapping[str, Any]) -> Application:
    environment = body.get("environment") or {}
    health = body.get("health") or {}
    return Application(
        name=name,
        component=str(body.get("component", "")),
        host=str(body.get("host", "") or ""),
        dockerfile=str(body.get("dockerfile", "") or ""),
        managed=str(body.get("managed", "") or ""),
        command=str(body.get("command", "") or ""),
        pre_deploy=str(body.get("pre_deploy", "") or ""),
        health=Health(
            liveness=str(health.get("liveness", "") or ""),
            readiness=str(health.get("readiness", "") or ""),
            stop_grace_period=str(health.get("stop_grace_period", "") or ""),
        ),
        volumes=tuple(
            Volume(name=str(one.get("name", "")), path=str(one.get("path", "")))
            for one in (body.get("volumes") or [])
        ),
        required=tuple(str(one) for one in (environment.get("required") or [])),
        optional=tuple(str(one) for one in (environment.get("optional") or [])),
        values={str(key): str(value) for key, value in (environment.get("values") or {}).items()},
    )


# --------------------------------------------------------------------------
# The checks, one clause of the specification each
# --------------------------------------------------------------------------


def exactly_four(inventory: Inventory) -> tuple[str, ...]:
    """*"exactly four components ... and no other without a specification change"*."""
    declared, expected = set(inventory.components), set(COMPONENTS)
    findings = [
        f"{name} is declared as a hosted application and {SPECIFICATION} names no "
        "such component: adding one to the hosted inventory is a specification change"
        for name in sorted(declared - expected)
    ]
    findings += [
        f"the hosted inventory is missing {name}, which {SPECIFICATION} requires"
        for name in sorted(expected - declared)
    ]
    return tuple(findings)


def nothing_unhostable_is_hosted(inventory: Inventory) -> tuple[str, ...]:
    """*"SHALL NOT be deployed as network-reachable services, in any environment"*."""
    findings = [
        f"{one.name} deploys {one.component}, which {SPECIFICATION} says is never "
        "hosted: the agent server is stdio and local-first, and exposing it over "
        "the network is a specification change rather than a configuration change"
        for one in inventory.applications
        if one.component in NEVER_HOSTED
    ]
    findings += [
        f"{name} is not recorded as deliberately un-hosted, with a reason"
        for name in NEVER_HOSTED
        if not inventory.never_hosted.get(name)
    ]
    return tuple(findings)


def hosts_follow_the_convention(inventory: Inventory) -> tuple[str, ...]:
    """*"reachable under the studio's deployment host convention"*."""
    findings = []
    for one in inventory.applications:
        reachable = one.component in REACHABLE
        if reachable and not one.host.endswith(inventory.host_suffix):
            findings.append(f"{one.name} is reachable and its host is not under the convention")
        if not reachable and one.host:
            findings.append(f"{one.name} is internal and SHOULD carry no public host")
    return tuple(findings)


def signals_are_distinct(inventory: Inventory) -> tuple[str, ...]:
    """*"Every deployed service SHALL expose two separate signals"* (D2)."""
    findings = []
    for one in inventory.applications:
        if one.component not in REACHABLE:
            continue
        if (one.health.liveness, one.health.readiness) != (LIVENESS, READINESS):
            findings.append(
                f"{one.name} does not point the restart probe at {LIVENESS} and the "
                f"routing gate at {READINESS}; conflating them restarts an instance "
                "that is merely not ready yet"
            )
    return tuple(findings)


def state_is_on_a_volume(inventory: Inventory) -> tuple[str, ...]:
    """*"the index database, the blob store and each project's working copy"*."""
    findings = []
    api = inventory.by_component(HTTP_API)
    if api is None or WORKTREES not in api.paths:
        findings.append(f"the API application does not mount the working copies at {WORKTREES}")
    for component in (INDEX_DATABASE, BLOB_STORE):
        application = inventory.by_component(component)
        if application is None or not application.volumes:
            findings.append(f"{component} has no persistent volume, so a redeploy would lose it")
    return tuple(findings)


def the_release_step_is_not_a_start_step(inventory: Inventory) -> tuple[str, ...]:
    """*"Migrations ... SHALL NOT run on service start"* (D4)."""
    api = inventory.by_component(HTTP_API)
    if api is None:
        return ()
    findings = []
    if api.pre_deploy.strip() != MIGRATE:
        findings.append(f"the API application's pre-deploy command is not {MIGRATE!r}")
    if "migrate" in api.command:
        findings.append(
            "the API application's start command migrates, which would migrate once "
            "per instance — no instance SHALL attempt a migration"
        )
    return tuple(findings)


def the_drain_window_is_the_platforms_too(inventory: Inventory) -> tuple[str, ...]:
    """D7 — *"the platform's window and the service's are the same number"*."""
    api = inventory.by_component(HTTP_API)
    if api is None or api.health.stop_grace_period == DRAIN_WINDOW:
        return ()
    return (
        f"the API application's stop grace period is not {DRAIN_WINDOW}, so the "
        "platform could terminate an instance before its write-back budget expires",
    )


def the_model_endpoint_stays_on_the_premises(inventory: Inventory) -> tuple[str, ...]:
    """`project.md` — the gateway is reached from inside the deployment network."""
    api = inventory.by_component(HTTP_API)
    if api is None:
        return ()
    endpoint = api.values.get("CANON_LLM_BASE_URL", "")
    if endpoint and inventory.host_suffix in endpoint:
        return ()
    return (
        "CANON_LLM_BASE_URL does not name an endpoint inside the deployment "
        "network: concept art is unreleased intellectual property, and the "
        "on-prem gateway is what keeps it on the premises",
    )


def environments_match_the_settings(
    inventory: Inventory,
    *,
    required: Sequence[str],
    optional: Sequence[str],
    web_required: Sequence[str],
) -> tuple[str, ...]:
    """D1's accepted cost, paid: the lists and the code name the same variables."""
    findings = _matches(inventory.by_component(HTTP_API), "required", required)
    findings += _matches(inventory.by_component(HTTP_API), "optional", optional)
    findings += _matches(inventory.by_component(WEB_APPLICATION), "required", web_required)
    return findings


def _matches(
    application: Application | None, which: str, expected: Sequence[str]
) -> tuple[str, ...]:
    if application is None:
        return ()
    declared = set(getattr(application, which))
    findings = [
        f"{application.name} is given {name}, which no service reads"
        for name in sorted(declared - set(expected))
    ]
    findings += [
        f"{application.name} is not given {name}, which it reads as {which}"
        for name in sorted(set(expected) - declared)
    ]
    return tuple(findings)


CHECKS = (
    exactly_four,
    nothing_unhostable_is_hosted,
    hosts_follow_the_convention,
    signals_are_distinct,
    state_is_on_a_volume,
    the_release_step_is_not_a_start_step,
    the_drain_window_is_the_platforms_too,
    the_model_endpoint_stays_on_the_premises,
)
"""Every clause that does not need to know what the settings model declares."""


def findings(
    inventory: Inventory,
    *,
    required: Sequence[str],
    optional: Sequence[str],
    web_required: Sequence[str],
) -> tuple[str, ...]:
    """Everything non-conforming about this declaration. Empty means conforming."""
    found: tuple[str, ...] = ()
    for check in CHECKS:
        found += check(inventory)
    return found + environments_match_the_settings(
        inventory, required=required, optional=optional, web_required=web_required
    )


__all__ = [
    "AGENT_SERVER",
    "BLOB_STORE",
    "COMMAND_LINE",
    "COMPONENTS",
    "HTTP_API",
    "INDEX_DATABASE",
    "MANIFEST_PATH",
    "NEVER_HOSTED",
    "WEB_APPLICATION",
    "Application",
    "Health",
    "Inventory",
    "Volume",
    "findings",
    "load",
]
