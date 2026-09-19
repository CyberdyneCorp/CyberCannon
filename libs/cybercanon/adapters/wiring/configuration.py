"""Configuration from the environment, with no file fallback.

`project.md` is unambiguous about this and about why: *"Configuration is
environment variables, with no file fallback. Coolify supplies configuration as
environment; twelve-factor is the native shape here, not an aspiration. No
secret is ever committed, and no configuration is baked into an image."*

Three properties follow, and each is a test rather than a convention:

* **No file is read.** Nothing here opens a path, and nothing falls back to one.
  A `.env` sitting beside the service is not configuration; it is a file
  somebody left there, and the day it disagrees with the environment is the day
  a deployment behaves differently from how it is described.
* **A missing variable names itself, and so does every other one.** The service
  refuses to start listing *all* the variables it needs and does not have.
  Failing on the first one turns configuring a new deployment into a queue of
  restarts, which is how people end up putting secrets in an image to make the
  loop shorter.
* **A secret never renders.** :class:`Secret` keeps its value out of `repr`,
  `str` and therefore out of every log line and stack trace, exactly as
  :class:`~cybercanon.application.ports.identity_provider.Credential` does.

The composition root reads this; the inbound HTTP adapter does not. An
application that needed configuration to answer whether it is alive would make
`http-api`'s readiness rule impossible to satisfy, so :func:`load` is called by
the deployable's entry point and the app is built either way.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from cybercanon.application.errors import FailureKind, OperationFailed

PREFIX = "CANON_"
"""Every variable this service reads is namespaced, so nothing collides."""


@dataclass(frozen=True)
class Secret:
    """A configured credential. Present, comparable, and never printed."""

    value: str = field(repr=False)

    def __str__(self) -> str:
        return "<secret>"

    def __bool__(self) -> bool:
        return bool(self.value)


class ConfigurationIncomplete(OperationFailed):
    """The service cannot start: these variables are required and absent.

    Every one of them, in one message. A loader that stopped at the first
    missing variable would make bringing up a deployment an exercise in
    restarting until the list runs out.
    """

    kind = FailureKind.INVALID
    identifier = "configuration.incomplete"

    def __init__(self, missing: Sequence[str]) -> None:
        listed = ", ".join(missing)
        super().__init__(
            f"the service cannot start: {len(missing)} required environment "
            f"variable(s) are not set — {listed}. Configuration is environment "
            "variables with no file fallback.",
            listed,
        )
        self.missing = tuple(missing)


class ConfigurationInvalid(OperationFailed):
    """A variable is set to something that cannot be read as what it must be."""

    kind = FailureKind.INVALID
    identifier = "configuration.invalid"

    def __init__(self, name: str, value: str, expected: str) -> None:
        super().__init__(f"{name} is {value!r}, which is not {expected}", name)
        self.name = name


@dataclass(frozen=True)
class RepositoryConfig:
    """Where a project's repository is, which branch is written, and how to reach it."""

    url: str
    branch: str
    credential: Secret
    fetch_interval: timedelta
    webhook_secret: Secret


@dataclass(frozen=True)
class IdentityConfig:
    """The issuer this service trusts, and how its groups become roles (D12).

    `group_roles` is configuration rather than code because `auth-integration`
    requires it: *"the translation ... SHALL be driven by configuration rather
    than by code that names specific groups"*, and a group with no mapping
    grants nothing.
    """

    issuer: str
    audience: str
    key_set_url: str
    group_roles: Mapping[str, str]


@dataclass(frozen=True)
class StorageConfig:
    """Where the rebuildable index and the blob mirror live, and how long links last."""

    database_url: Secret
    object_store_url: str
    link_expiry: timedelta


@dataclass(frozen=True)
class ServiceConfiguration:
    """Everything the hosted service needs, already read and already checked."""

    repository: RepositoryConfig
    identity: IdentityConfig
    storage: StorageConfig


REQUIRED: tuple[str, ...] = (
    "CANON_REPOSITORY_URL",
    "CANON_REPOSITORY_BRANCH",
    "CANON_REPOSITORY_CREDENTIAL",
    "CANON_FETCH_INTERVAL_S",
    "CANON_WEBHOOK_SECRET",
    "CANON_AUTH_ISSUER",
    "CANON_AUTH_AUDIENCE",
    "CANON_AUTH_KEY_SET_URL",
    "CANON_AUTH_GROUP_ROLES",
    "CANON_DATABASE_URL",
    "CANON_OBJECT_STORE_URL",
    "CANON_LINK_EXPIRY_S",
)
"""Every variable the service refuses to start without.

Exactly the twelve task 1.4 enumerates — repository, branch, credential, fetch
interval, webhook secret, issuer, audience, key set URL, group mapping,
database, object store, link expiry — as one literal, so "what does this service
need" has a single answer that a test can read.
"""

GROUP_SEPARATOR = ","
PAIR_SEPARATOR = "="


def load(environment: Mapping[str, str] | None = None) -> ServiceConfiguration:
    """Read the configuration, or refuse to start naming everything that is missing.

    `environment` defaults to the process environment and is a parameter only so
    a test can hand in a mapping — never so a caller can supply a file. There is
    no path in this signature and no path in this module.
    """
    source = os.environ if environment is None else environment
    missing = tuple(name for name in REQUIRED if not source.get(name, "").strip())
    if missing:
        raise ConfigurationIncomplete(missing)
    return ServiceConfiguration(
        repository=RepositoryConfig(
            url=source["CANON_REPOSITORY_URL"],
            branch=source["CANON_REPOSITORY_BRANCH"],
            credential=Secret(source["CANON_REPOSITORY_CREDENTIAL"]),
            fetch_interval=_seconds(source, "CANON_FETCH_INTERVAL_S"),
            webhook_secret=Secret(source["CANON_WEBHOOK_SECRET"]),
        ),
        identity=IdentityConfig(
            issuer=source["CANON_AUTH_ISSUER"],
            audience=source["CANON_AUTH_AUDIENCE"],
            key_set_url=source["CANON_AUTH_KEY_SET_URL"],
            group_roles=group_roles(source["CANON_AUTH_GROUP_ROLES"]),
        ),
        storage=StorageConfig(
            database_url=Secret(source["CANON_DATABASE_URL"]),
            object_store_url=source["CANON_OBJECT_STORE_URL"],
            link_expiry=_seconds(source, "CANON_LINK_EXPIRY_S"),
        ),
    )


def missing_from(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Which required variables this environment does not set, in declared order."""
    return tuple(name for name in REQUIRED if not environment.get(name, "").strip())


def group_roles(declared: str) -> Mapping[str, str]:
    """`group=ROLE,group=ROLE` as a mapping, with no opinion about either side.

    Roles are not validated here and groups are not named in code, which is the
    whole point of D12: an unmapped group grants nothing, and adding a mapping
    is a configuration change rather than a deploy. A pair this cannot read at
    all is a configuration error, because silently dropping it would grant
    nothing while looking like it granted something.
    """
    pairs = [entry.strip() for entry in declared.split(GROUP_SEPARATOR) if entry.strip()]
    mapping: dict[str, str] = {}
    for pair in pairs:
        group, separator, role = pair.partition(PAIR_SEPARATOR)
        if not separator or not group.strip() or not role.strip():
            raise ConfigurationInvalid("CANON_AUTH_GROUP_ROLES", pair, "a `group=ROLE` pair")
        mapping[group.strip()] = role.strip()
    return mapping


def _seconds(source: Mapping[str, str], name: str) -> timedelta:
    """A duration in whole seconds, or a refusal naming the variable."""
    raw = source[name]
    try:
        value = int(raw)
    except ValueError as failure:
        raise ConfigurationInvalid(name, raw, "a whole number of seconds") from failure
    if value <= 0:
        raise ConfigurationInvalid(name, raw, "a positive number of seconds")
    return timedelta(seconds=value)


__all__ = [
    "GROUP_SEPARATOR",
    "PAIR_SEPARATOR",
    "PREFIX",
    "REQUIRED",
    "ConfigurationIncomplete",
    "ConfigurationInvalid",
    "IdentityConfig",
    "RepositoryConfig",
    "Secret",
    "ServiceConfiguration",
    "StorageConfig",
    "group_roles",
    "load",
    "missing_from",
]
