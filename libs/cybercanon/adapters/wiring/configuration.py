"""Configuration from the environment, with no file fallback.

`project.md` is unambiguous about this and about why: *"Configuration is
environment variables, with no file fallback. Coolify supplies configuration as
environment; twelve-factor is the native shape here, not an aspiration. No
secret is ever committed, and no configuration is baked into an image."*

`deployment-operations` then states the carve-out that keeps the rule honest:
**a project's own settings file inside its working copy is repository content,
not service configuration.** That file is read through the `SpecStore`, at a
revision, like every other piece of content; nothing in this module can reach
it, and nothing in this module can reach any other file either.

Four properties follow, and each is a test rather than a convention:

* **No file is read.** Nothing here opens a path, and nothing falls back to one.
  A `.env` sitting beside the service, or baked into the image, is not
  configuration; it is a file somebody left there, and the day it disagrees with
  the environment is the day a deployment behaves differently from how it is
  described.
* **Every offending variable names itself, in one message.** Missing *and*
  malformed, together, with the shape a malformed one was expected to have. The
  service refuses to start listing all of them, because failing on the first one
  turns configuring a new deployment into a queue of restarts — which is how
  people end up putting secrets in an image to make the loop shorter.
* **A value is never echoed.** :class:`Secret` keeps its value out of `repr`,
  `str` and therefore out of every log line and stack trace, exactly as
  :class:`~cybercanon.application.ports.identity_provider.Credential` does; and
  a refusal names the setting and the shape it wanted, never what was there. The
  expected shape is the actionable half, and a message that quoted the value
  would leak a credential the first time one was mistyped.
* **Optional configuration is absent, not broken.** The language model settings
  have a master switch defaulting to off (`project.md`), so a deployment that
  configures none of them starts, and the features that need one report
  themselves unavailable rather than taking the service down with them.

The composition root reads this; the inbound HTTP adapter does not. An
application that needed configuration to answer whether it is alive would make
`http-api`'s readiness rule impossible to satisfy, so :func:`load` is called by
the deployable's entry point and the app is built either way.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

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


@dataclass(frozen=True)
class Problem:
    """One variable the service cannot start with, and what it wanted instead.

    `present` distinguishes the two cases the specification distinguishes: a
    setting that is *absent* names itself, and one that is *malformed* names
    itself **and** the expected shape. Neither carries the value.
    """

    name: str
    expected: str
    present: bool

    def __str__(self) -> str:
        return f"{self.name} is {'not ' + self.expected if self.present else 'not set'}"


class ConfigurationRejected(OperationFailed):
    """The service cannot start with this environment. Base of the two cases."""

    kind = FailureKind.INVALID
    identifier = "configuration.rejected"

    def __init__(self, message: str, subject: str, problems: Sequence[Problem]) -> None:
        super().__init__(message, subject)
        self.problems = tuple(problems)

    @property
    def names(self) -> tuple[str, ...]:
        """Every offending variable, in the order they are declared."""
        return tuple(problem.name for problem in self.problems)


class ConfigurationIncomplete(ConfigurationRejected):
    """The service cannot start: these variables are required and absent.

    Every one of them, in one message. A loader that stopped at the first
    missing variable would make bringing up a deployment an exercise in
    restarting until the list runs out.
    """

    identifier = "configuration.incomplete"

    def __init__(self, missing: Sequence[str]) -> None:
        listed = ", ".join(missing)
        super().__init__(
            f"the service cannot start: {len(missing)} required environment "
            f"variable(s) are not set — {listed}. Configuration is environment "
            "variables with no file fallback.",
            listed,
            tuple(Problem(name, "", present=False) for name in missing),
        )
        self.missing = tuple(missing)


class ConfigurationInvalid(ConfigurationRejected):
    """At least one variable is set to something that cannot be read as what it must be.

    Missing variables travel in the same message, because a deployment with one
    of each has two things to fix and deserves to learn both at once.
    """

    identifier = "configuration.invalid"

    def __init__(self, problems: Sequence[Problem]) -> None:
        listed = "; ".join(str(problem) for problem in problems)
        super().__init__(
            f"the service cannot start: {len(problems)} environment variable(s) "
            f"are wrong — {listed}. No value is quoted here on purpose.",
            problems[0].name,
            problems,
        )
        self.name = problems[0].name

    @classmethod
    def of(cls, name: str, expected: str) -> ConfigurationInvalid:
        """One malformed setting on its own, for a reader called outside :func:`read`."""
        return cls((Problem(name, expected, present=True),))


# --------------------------------------------------------------------------
# Readers: one per shape, each raising `ValueError` and naming nothing
# --------------------------------------------------------------------------

GROUP_SEPARATOR = ","
PAIR_SEPARATOR = "="

SCHEME_SEPARATOR = "://"

TRUE = ("1", "true", "yes", "on")
FALSE = ("0", "false", "no", "off")


def text(raw: str) -> str:
    """Any non-empty string. The shape of a name somebody else defined."""
    return raw


def url(raw: str) -> str:
    """An endpoint with a scheme — `postgresql://…`, `https://…`."""
    scheme, separator, rest = raw.partition(SCHEME_SEPARATOR)
    if not separator or not scheme.strip() or not rest.strip():
        raise ValueError("expected a scheme")
    return raw


def seconds(raw: str) -> timedelta:
    """A duration in whole, positive seconds."""
    value = int(raw)
    if value <= 0:
        raise ValueError("expected a positive number")
    return timedelta(seconds=value)


def count(raw: str) -> int:
    """A whole number of attempts, zero included."""
    value = int(raw)
    if value < 0:
        raise ValueError("expected zero or more")
    return value


def flag(raw: str) -> bool:
    """A switch. Anything else is a misconfiguration, not a quiet `False`."""
    lowered = raw.strip().lower()
    if lowered in TRUE:
        return True
    if lowered in FALSE:
        return False
    raise ValueError("expected a switch")


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
            raise ConfigurationInvalid.of(GROUP_ROLES, "a list of `group=ROLE` pairs")
        mapping[group.strip()] = role.strip()
    return mapping


def _pairs(raw: str) -> Mapping[str, str]:
    """The reader form of :func:`group_roles`, for the declaration table."""
    return group_roles(raw)


# --------------------------------------------------------------------------
# The declaration: one row per variable, and the only list of them
# --------------------------------------------------------------------------

type Reader = Callable[[str], Any]


@dataclass(frozen=True)
class Setting:
    """One environment variable: how it is read, what it is for, whether it is secret.

    `expected` is prose rather than a type, because it is what a person reads at
    three in the morning when a deployment refused to start.
    """

    name: str
    expected: str
    read: Reader = text
    required: bool = True
    secret: bool = False
    default: Any = None


REPOSITORY_URL = "CANON_REPOSITORY_URL"
REPOSITORY_BRANCH = "CANON_REPOSITORY_BRANCH"
REPOSITORY_CREDENTIAL = "CANON_REPOSITORY_CREDENTIAL"
FETCH_INTERVAL = "CANON_FETCH_INTERVAL_S"
WEBHOOK_SECRET = "CANON_WEBHOOK_SECRET"
AUTH_ISSUER = "CANON_AUTH_ISSUER"
AUTH_AUDIENCE = "CANON_AUTH_AUDIENCE"
AUTH_KEY_SET_URL = "CANON_AUTH_KEY_SET_URL"
AUTH_KEY_CACHE_TTL = "CANON_AUTH_KEY_CACHE_TTL_S"
GROUP_ROLES = "CANON_AUTH_GROUP_ROLES"
DATABASE_URL = "CANON_DATABASE_URL"
OBJECT_STORE_URL = "CANON_OBJECT_STORE_URL"
LINK_EXPIRY = "CANON_LINK_EXPIRY_S"
WRITE_BACK_TIMEOUT = "CANON_WRITE_BACK_TIMEOUT_S"
DRAIN_WINDOW = "CANON_DRAIN_WINDOW_S"

MODEL_ENABLED = "CANON_LLM_ENABLED"
MODEL_BASE_URL = "CANON_LLM_BASE_URL"
MODEL_API_KEY = "CANON_LLM_API_KEY"
MODEL_NAME = "CANON_LLM_MODEL"
MODEL_VISION_NAME = "CANON_LLM_VISION_MODEL"
MODEL_TIMEOUT = "CANON_LLM_TIMEOUT_S"
MODEL_MAX_RETRIES = "CANON_LLM_MAX_RETRIES"

SETTINGS: tuple[Setting, ...] = (
    Setting(REPOSITORY_URL, "a git remote the service can reach"),
    Setting(REPOSITORY_BRANCH, "the branch write-backs are committed to"),
    Setting(REPOSITORY_CREDENTIAL, "a deploy credential for that remote", secret=True),
    Setting(FETCH_INTERVAL, "a whole number of seconds", read=seconds),
    Setting(WEBHOOK_SECRET, "the shared secret the git host signs with", secret=True),
    Setting(AUTH_ISSUER, "the issuer this service trusts"),
    Setting(AUTH_AUDIENCE, "the audience this service is addressed as"),
    Setting(AUTH_KEY_SET_URL, "a URL of the form scheme://host/path", read=url),
    Setting(GROUP_ROLES, "a list of `group=ROLE` pairs", read=_pairs),
    Setting(AUTH_KEY_CACHE_TTL, "a whole number of seconds", read=seconds, required=False),
    Setting(DATABASE_URL, "a connection string of the form scheme://host", read=url, secret=True),
    Setting(OBJECT_STORE_URL, "a URL of the form scheme://host", read=url),
    Setting(LINK_EXPIRY, "a whole number of seconds", read=seconds),
    Setting(WRITE_BACK_TIMEOUT, "a whole number of seconds", read=seconds),
    Setting(DRAIN_WINDOW, "a whole number of seconds", read=seconds),
    Setting(MODEL_ENABLED, "a switch", read=flag, required=False, default=False),
    Setting(MODEL_BASE_URL, "an OpenAI-compatible endpoint", read=url, required=False, default=""),
    Setting(MODEL_API_KEY, "a bearer credential", required=False, secret=True, default=""),
    Setting(MODEL_NAME, "a model identifier, passed through verbatim", required=False, default=""),
    Setting(MODEL_VISION_NAME, "a multimodal model identifier", required=False, default=""),
    Setting(MODEL_TIMEOUT, "a whole number of seconds", read=seconds, required=False),
    Setting(MODEL_MAX_RETRIES, "a whole number of attempts", read=count, required=False, default=2),
)
"""Every variable this service reads, required and optional, in one table.

The required fourteen — repository, branch, credential, fetch interval,
webhook secret, issuer, audience, key set URL, group mapping, database, object
store, link expiry, write-back timeout, drain window — are what the service
refuses to start without. The last two are a *pair*: D7 makes "a commit or
nothing" a property of two configured numbers in a known order, so they are
read together and checked against each other (:class:`RolloverConfig`).

The seven model variables are optional by `project.md`'s rule that *"the
system SHALL be fully usable with it off"*, and the key-cache window is optional
because D8 fixes the *behaviour* — existing credentials keep verifying while the
issuer is unreachable — and leaves the number to the deployment. `deploy/README.md`
is checked against this table so the document and the code cannot drift, and so
is `deploy/coolify.yaml`, which is what each application is actually given.
"""

REQUIRED: tuple[str, ...] = tuple(setting.name for setting in SETTINGS if setting.required)
"""The variables a boot fails without, in declared order."""

OPTIONAL: tuple[str, ...] = tuple(setting.name for setting in SETTINGS if not setting.required)
"""The variables whose absence is a feature being off, not a broken deployment."""

SECRETS: tuple[str, ...] = tuple(setting.name for setting in SETTINGS if setting.secret)
"""The variables whose values may never appear in a message, a log or an artifact."""

DEFAULT_MODEL_TIMEOUT = timedelta(seconds=30)

DEFAULT_KEY_CACHE_TTL = timedelta(minutes=15)
"""How long cached signing keys keep verifying while the issuer is unreachable.

D8 in one number: *"the `IdentityProvider` adapter caches the signing keys
with a TTL and continues verifying existing tokens while the provider is
unreachable"*, and *"a bounded window where a key rotated during an outage is
not yet known, ending at the TTL"*. Fifteen minutes is long enough that a
restart of the identity service is invisible to everybody using the tool and
short enough that a revoked key stops being honoured inside a coffee break —
and it is a *default* rather than a constant, because which of those two costs
a studio would rather pay is a deployment decision.
"""


# --------------------------------------------------------------------------
# The configuration itself
# --------------------------------------------------------------------------


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
    key_cache_ttl: timedelta = DEFAULT_KEY_CACHE_TTL


@dataclass(frozen=True)
class StorageConfig:
    """Where the rebuildable index and the blob mirror live, and how long links last."""

    database_url: Secret
    object_store_url: str
    link_expiry: timedelta


ROLLOVER_ORDER = (
    "the drain window must be longer than the write-back budget, so a write-back "
    "accepted just before retirement either lands inside the window or is "
    "abandoned by its own timeout before the instance is terminated"
)
"""D7, as the sentence a refused boot prints. The ordering is the mechanism."""


@dataclass(frozen=True)
class RolloverConfig:
    """The two numbers a zero-downtime rollover is made of (D7).

    Coolify starts the new instance, waits for `/readyz`, routes to it, then
    signals the old one, which stops accepting requests and drains.
    :attr:`drain_window` is how long that draining is allowed to take and
    :attr:`write_back_timeout` is how long one write-back may take before it
    gives up and resets the working copy.

    **The order between them is the guarantee, not a recommendation.** *"An
    interrupted write-back leaves a commit or leaves nothing"* is true because
    the timeout fires first: a write-back accepted a moment before retirement
    either finishes inside the window, or abandons itself — and abandoning
    resets the working copy — before anything terminates the process. Inverted,
    the container would be killed with a half-applied edit on the volume, which
    is precisely the state the specification forbids. So an inverted pair is a
    refused boot naming both variables, rather than a sentence in a document
    nobody re-reads.
    """

    write_back_timeout: timedelta
    drain_window: timedelta

    @property
    def drains_longer_than_write_back(self) -> bool:
        """Whether the pair is in the order D7 requires."""
        return self.drain_window > self.write_back_timeout

    @property
    def headroom(self) -> timedelta:
        """What the drain window has left after the longest permitted write-back."""
        return self.drain_window - self.write_back_timeout


def rollover_problems(rollover: RolloverConfig) -> tuple[Problem, ...]:
    """The refusal an out-of-order pair earns, naming both variables.

    Both, because either one could be the one that is wrong and the person
    reading the message is the one who knows which.
    """
    if rollover.drains_longer_than_write_back:
        return ()
    return (
        Problem(WRITE_BACK_TIMEOUT, f"shorter than {DRAIN_WINDOW}: {ROLLOVER_ORDER}", present=True),
        Problem(DRAIN_WINDOW, f"longer than {WRITE_BACK_TIMEOUT}: {ROLLOVER_ORDER}", present=True),
    )


@dataclass(frozen=True)
class ModelConfig:
    """The language model, which is off until somebody turns it on.

    `project.md`: *"Every LLM feature degrades to absent. Disabled,
    misconfigured, timing out or rate-limited SHALL all behave the same way: the
    feature is unavailable and everything else works."* :attr:`available` is
    that sentence as one expression, so no caller re-derives it.
    """

    enabled: bool = False
    base_url: str = ""
    api_key: Secret = Secret("")
    model: str = ""
    vision_model: str = ""
    timeout: timedelta = DEFAULT_MODEL_TIMEOUT
    max_retries: int = 2

    @property
    def available(self) -> bool:
        """Whether a model-dependent feature can be attempted at all."""
        return bool(self.enabled and self.base_url and self.model)

    @property
    def absence(self) -> str:
        """Why it is unavailable, for the status surface to state."""
        if not self.enabled:
            return f"{MODEL_ENABLED} is off"
        if not self.base_url or not self.model:
            return f"{MODEL_BASE_URL} and {MODEL_NAME} are not both set"
        return ""


@dataclass(frozen=True)
class ServiceConfiguration:
    """Everything the hosted service needs, already read and already checked."""

    repository: RepositoryConfig
    identity: IdentityConfig
    storage: StorageConfig
    rollover: RolloverConfig
    model: ModelConfig = ModelConfig()


def load(environment: Mapping[str, str] | None = None) -> ServiceConfiguration:
    """Read the configuration, or refuse to start naming everything that is wrong.

    `environment` defaults to the process environment and is a parameter only so
    a test can hand in a mapping — never so a caller can supply a file. There is
    no path in this signature and no path in this module.
    """
    source = os.environ if environment is None else environment
    values = read(source)
    rollover = RolloverConfig(
        write_back_timeout=values[WRITE_BACK_TIMEOUT],
        drain_window=values[DRAIN_WINDOW],
    )
    problems = rollover_problems(rollover)
    if problems:
        raise refusal(problems)
    return ServiceConfiguration(
        repository=RepositoryConfig(
            url=values[REPOSITORY_URL],
            branch=values[REPOSITORY_BRANCH],
            credential=Secret(values[REPOSITORY_CREDENTIAL]),
            fetch_interval=values[FETCH_INTERVAL],
            webhook_secret=Secret(values[WEBHOOK_SECRET]),
        ),
        identity=IdentityConfig(
            issuer=values[AUTH_ISSUER],
            audience=values[AUTH_AUDIENCE],
            key_set_url=values[AUTH_KEY_SET_URL],
            group_roles=values[GROUP_ROLES],
            key_cache_ttl=values[AUTH_KEY_CACHE_TTL] or DEFAULT_KEY_CACHE_TTL,
        ),
        storage=StorageConfig(
            database_url=Secret(values[DATABASE_URL]),
            object_store_url=values[OBJECT_STORE_URL],
            link_expiry=values[LINK_EXPIRY],
        ),
        rollover=rollover,
        model=ModelConfig(
            enabled=values[MODEL_ENABLED],
            base_url=values[MODEL_BASE_URL],
            api_key=Secret(values[MODEL_API_KEY]),
            model=values[MODEL_NAME],
            vision_model=values[MODEL_VISION_NAME],
            timeout=values[MODEL_TIMEOUT] or DEFAULT_MODEL_TIMEOUT,
            max_retries=values[MODEL_MAX_RETRIES],
        ),
    )


def read(source: Mapping[str, str]) -> Mapping[str, Any]:
    """Every declared setting, read once, or one refusal carrying all the problems."""
    values: dict[str, Any] = {}
    problems: list[Problem] = []
    for setting in SETTINGS:
        problem = _value_of(setting, source, values)
        if problem is not None:
            problems.append(problem)
    if problems:
        raise refusal(problems)
    return values


def _value_of(
    setting: Setting, source: Mapping[str, str], values: dict[str, Any]
) -> Problem | None:
    """Read one setting into `values`, or say what is wrong with it."""
    raw = source.get(setting.name, "").strip()
    if not raw:
        if setting.required:
            return Problem(setting.name, setting.expected, present=False)
        values[setting.name] = setting.default
        return None
    try:
        values[setting.name] = setting.read(raw)
    except (ValueError, ConfigurationRejected):
        return Problem(setting.name, setting.expected, present=True)
    return None


def refusal(problems: Sequence[Problem]) -> ConfigurationRejected:
    """The one error a refused boot raises: incomplete when nothing was malformed."""
    if all(not problem.present for problem in problems):
        return ConfigurationIncomplete(tuple(problem.name for problem in problems))
    return ConfigurationInvalid(tuple(problems))


def missing_from(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Which required variables this environment does not set, in declared order."""
    return tuple(name for name in REQUIRED if not environment.get(name, "").strip())


__all__ = [
    "DEFAULT_KEY_CACHE_TTL",
    "DEFAULT_MODEL_TIMEOUT",
    "GROUP_SEPARATOR",
    "OPTIONAL",
    "PAIR_SEPARATOR",
    "PREFIX",
    "REQUIRED",
    "ROLLOVER_ORDER",
    "SECRETS",
    "SETTINGS",
    "ConfigurationIncomplete",
    "ConfigurationInvalid",
    "ConfigurationRejected",
    "IdentityConfig",
    "ModelConfig",
    "Problem",
    "RepositoryConfig",
    "RolloverConfig",
    "Secret",
    "ServiceConfiguration",
    "Setting",
    "StorageConfig",
    "group_roles",
    "load",
    "missing_from",
    "read",
    "refusal",
    "rollover_problems",
]
