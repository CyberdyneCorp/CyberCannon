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

WILDCARD = "*"
"""What a browser origin may never be configured as."""

DEFAULT_WORKING_COPIES = "/data/worktrees"
"""Where the persistent working copies live, matching `deploy/coolify.yaml`.

A default rather than a required variable because it is the *volume's* mount
point and it is declared in the deployment manifest, which the inventory check
already reads against this module. An operator who mounts it elsewhere says so;
one who follows the manifest does not have to.
"""

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


def origins(raw: str) -> tuple[str, ...]:
    """A comma-separated list of browser origins, each `scheme://host[:port]`.

    A wildcard is refused rather than honoured. `deploy/coolify.yaml` puts the
    API and the web application on different hosts, so the browser asks this
    service whether the application's origin may read it — and the honest answer
    is a list somebody wrote down, per environment. `*` would be the answer that
    is the same everywhere and true nowhere, and it cannot carry credentials at
    all, which is precisely what this surface's requests do.
    """
    declared = [entry.strip().rstrip("/") for entry in raw.split(GROUP_SEPARATOR)]
    listed = [entry for entry in declared if entry]
    if not listed:
        raise ValueError("expected at least one origin")
    for entry in listed:
        if entry == WILDCARD:
            raise ValueError("expected an origin, not a wildcard")
        url(entry)
    return tuple(dict.fromkeys(listed))


def client_ids(raw: str) -> tuple[str, ...]:
    """A comma-separated list of client identifiers, deduplicated, order kept.

    Used by `CANON_AUTH_SERVICE_CLIENTS`, whose contents decide which background
    work this deployment trusts, so it reads strictly: a value that separates
    nothing — `,` or `, ,` — is a configuration error rather than an empty list,
    because somebody who wrote it meant to list something. *Unset* is the empty
    list and is a different statement: this deployment admits no automation.
    """
    listed = [entry.strip() for entry in raw.split(GROUP_SEPARATOR) if entry.strip()]
    if not listed:
        raise ValueError("expected at least one client id")
    return tuple(dict.fromkeys(listed))


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


PROJECT = "CANON_PROJECT"
REPOSITORY_URL = "CANON_REPOSITORY_URL"
REPOSITORY_BRANCH = "CANON_REPOSITORY_BRANCH"
REPOSITORY_CREDENTIAL = "CANON_REPOSITORY_CREDENTIAL"
FETCH_INTERVAL = "CANON_FETCH_INTERVAL_S"
WEBHOOK_SECRET = "CANON_WEBHOOK_SECRET"
AUTH_ISSUER = "CANON_AUTH_ISSUER"
AUTH_AUDIENCE = "CANON_AUTH_AUDIENCE"
AUTH_CLIENT_ID = "CANON_AUTH_CLIENT_ID"
AUTH_ORG_ID = "CANON_AUTH_ORG_ID"
AUTH_SERVICE_CLIENTS = "CANON_AUTH_SERVICE_CLIENTS"
AUTH_KEY_SET_URL = "CANON_AUTH_KEY_SET_URL"
AUTH_KEY_CACHE_TTL = "CANON_AUTH_KEY_CACHE_TTL_S"
GROUP_ROLES = "CANON_AUTH_GROUP_ROLES"
WORKER_CLIENT_ID = "CANON_WORKER_CLIENT_ID"
WORKER_CLIENT_SECRET = "CANON_WORKER_CLIENT_SECRET"
DATABASE_URL = "CANON_DATABASE_URL"
OBJECT_STORE_URL = "CANON_OBJECT_STORE_URL"
LINK_EXPIRY = "CANON_LINK_EXPIRY_S"
WRITE_BACK_TIMEOUT = "CANON_WRITE_BACK_TIMEOUT_S"
DRAIN_WINDOW = "CANON_DRAIN_WINDOW_S"
WORKING_COPIES = "CANON_WORKING_COPIES"
WEB_ORIGINS = "CANON_WEB_ORIGINS"

ARCHE_ENABLED = "CANON_ARCHE_ENABLED"
ARCHE_BASE_URL = "CANON_ARCHE_BASE_URL"
ARCHE_WORKSPACE = "CANON_ARCHE_DEFAULT_WORKSPACE"
ARCHE_TIMEOUT = "CANON_ARCHE_TIMEOUT_S"
ARCHE_WEB_URL = "CANON_ARCHE_WEB_URL"

MODEL_ENABLED = "CANON_LLM_ENABLED"
MODEL_BASE_URL = "CANON_LLM_BASE_URL"
MODEL_API_KEY = "CANON_LLM_API_KEY"
MODEL_NAME = "CANON_LLM_MODEL"
MODEL_VISION_NAME = "CANON_LLM_VISION_MODEL"
MODEL_TIMEOUT = "CANON_LLM_TIMEOUT_S"
MODEL_MAX_RETRIES = "CANON_LLM_MAX_RETRIES"

SETTINGS: tuple[Setting, ...] = (
    Setting(PROJECT, "the identifier this deployment serves its project as"),
    Setting(REPOSITORY_URL, "a git remote the service can reach"),
    Setting(REPOSITORY_BRANCH, "the branch write-backs are committed to"),
    Setting(REPOSITORY_CREDENTIAL, "a deploy credential for that remote", secret=True),
    Setting(FETCH_INTERVAL, "a whole number of seconds", read=seconds),
    Setting(WEBHOOK_SECRET, "the shared secret the git host signs with", secret=True),
    Setting(AUTH_ISSUER, "the issuer this service trusts"),
    Setting(AUTH_AUDIENCE, "the audience this service is addressed as"),
    Setting(AUTH_CLIENT_ID, "the client this deployment's roles are registered under"),
    Setting(AUTH_ORG_ID, "the identifier of the organisation this deployment serves"),
    Setting(AUTH_KEY_SET_URL, "a URL of the form scheme://host/path", read=url),
    Setting(GROUP_ROLES, "a list of `role=ROLE` pairs", read=_pairs),
    Setting(AUTH_KEY_CACHE_TTL, "a whole number of seconds", read=seconds, required=False),
    Setting(
        AUTH_SERVICE_CLIENTS,
        "a comma-separated list of service client ids",
        read=client_ids,
        required=False,
        default=(),
    ),
    Setting(WORKER_CLIENT_ID, "the client background work signs in as", required=False, default=""),
    Setting(
        WORKER_CLIENT_SECRET,
        "the secret that client authenticates with",
        required=False,
        secret=True,
        default="",
    ),
    Setting(DATABASE_URL, "a connection string of the form scheme://host", read=url, secret=True),
    Setting(OBJECT_STORE_URL, "a URL of the form scheme://host", read=url),
    Setting(LINK_EXPIRY, "a whole number of seconds", read=seconds),
    Setting(WRITE_BACK_TIMEOUT, "a whole number of seconds", read=seconds),
    Setting(DRAIN_WINDOW, "a whole number of seconds", read=seconds),
    Setting(
        WORKING_COPIES,
        "a directory on the working-copy volume",
        required=False,
        default=DEFAULT_WORKING_COPIES,
    ),
    Setting(
        WEB_ORIGINS,
        "a comma-separated list of `scheme://host` origins, never `*`",
        read=origins,
        required=False,
        default=(),
    ),
    Setting(MODEL_ENABLED, "a switch", read=flag, required=False, default=False),
    Setting(MODEL_BASE_URL, "an OpenAI-compatible endpoint", read=url, required=False, default=""),
    Setting(MODEL_API_KEY, "a bearer credential", required=False, secret=True, default=""),
    Setting(MODEL_NAME, "a model identifier, passed through verbatim", required=False, default=""),
    Setting(MODEL_VISION_NAME, "a multimodal model identifier", required=False, default=""),
    Setting(MODEL_TIMEOUT, "a whole number of seconds", read=seconds, required=False),
    Setting(MODEL_MAX_RETRIES, "a whole number of attempts", read=count, required=False, default=2),
    Setting(ARCHE_ENABLED, "a switch", read=flag, required=False, default=False),
    Setting(
        ARCHE_BASE_URL, "the document platform's API root", read=url, required=False, default=""
    ),
    Setting(
        ARCHE_WORKSPACE, "the workspace new documents are created in", required=False, default=""
    ),
    Setting(ARCHE_TIMEOUT, "a whole number of seconds", read=seconds, required=False),
    Setting(
        ARCHE_WEB_URL,
        "where a document is opened in a browser",
        read=url,
        required=False,
        default="",
    ),
)
"""Every variable this service reads, required and optional, in one table.

The required seventeen — project, repository, branch, credential, fetch
interval, webhook secret, issuer, audience, client id, organisation, key set
URL, role mapping, database, object store, link expiry, write-back timeout,
drain window — are what the service refuses to start without. The client id and
the organisation are required rather than optional because both fail *closed*:
an unset client id recognises no role in the `roles` claim and an unset
organisation admits nobody, so a deployment that omitted either would start,
sign people in and then show them nothing — which reads as an empty project
rather than as a misconfiguration, and is precisely the shape of green this
service has been bitten by before. `CANON_PROJECT` is required for the reason the others
are: a hosted API that serves no project answers health and nothing else, and
that is a deployment nobody notices is broken until somebody opens the web
application. The last two are a *pair*: D7 makes "a commit or
nothing" a property of two configured numbers in a known order, so they are
read together and checked against each other (:class:`RolloverConfig`).

The worker's two are optional, and optional as a pair: a deployment that
configures neither does its background work exactly as before, and one that
configures half of it behaves like the absence rather than failing once per
scheduled run (:class:`WorkerConfig`). The secret is declared `secret=True`, so
the scan that refuses a committed `CANON_REPOSITORY_CREDENTIAL` refuses this one
too.

The seven model variables are optional by `project.md`'s rule that *"the
system SHALL be fully usable with it off"*, and the five document-platform
variables are optional for the same reason and are **declared here but read by
`adapters/outbound/arche`**: the composition root chooses the null adapter
whenever they are absent or incomplete (add-cyberarche-integration D4), and
`canon` — which has no `ServiceConfiguration` at all — reads the same five from
its own environment. They are named in this table because this table is what
`deploy/README.md` and `deploy/coolify.yaml` are checked against, and a variable
an operator cannot find written down is a variable nobody sets; the working-copy volume is optional
because the deployment manifest declares where it is mounted; the browser
origins are optional because a deployment reached only by the command line and
the agent surface grants none; and the key-cache window is optional
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
    """Where a project's repository is, which branch is written, and how to reach it.

    `project` is the identifier this deployment serves the repository as, and it
    is *the address*: `http-api` requires every resource to be reachable at
    `/{version}/projects/{project}/…` for as long as it exists, so the name is
    configuration rather than something derived from a URL or read out of a file
    that a commit could change underneath a running service. Everything keyed by
    a project — the entitlement decision, the index rows, the working-copy
    directory — is keyed by this one string.
    """

    url: str
    branch: str
    credential: Secret
    fetch_interval: timedelta
    webhook_secret: Secret
    project: str = ""
    working_copies: str = DEFAULT_WORKING_COPIES


@dataclass(frozen=True)
class IdentityConfig:
    """The issuer this service trusts, who it is to that issuer, and its roles (D12).

    `group_roles` is configuration rather than code because `auth-integration`
    requires it: *"the translation ... SHALL be driven by configuration rather
    than by code that names specific groups"*, and a role key with no mapping
    grants nothing.

    `client_id` and `organisation` are the two the real token shape made
    necessary, and they are configuration for exactly the same reason.
    CyberdyneAuth writes **every** client's roles into one `roles` claim, each
    entry prefixed with the client it belongs to, so a deployment that did not
    know its own client id would either grant nothing or — far worse — grant
    somebody this project's art director because they are an art director in a
    different application. And a person reads this deployment's project only if
    their `orgs` claim carries `organisation`, which is an identifier in the
    identity service's database: writing one into this repository would tie the
    product to one studio and would have to be edited by the second.

    `service_clients` is the same kind of fact for the callers that are not
    people. A `type: service` token asserts only that there is no person behind
    it, and the issuer mints those for every client it knows — one registered
    with no audience restriction may request this deployment's audience and be
    given it. So this list, and not the token, is what says whose background
    work runs here. **Empty admits nothing**: a deployment that has not named
    its automation has none, and the refusal names the variable rather than
    reading as a broken credential. The other reading — empty admitting anything
    — is the defect this setting exists to close.
    """

    issuer: str
    audience: str
    key_set_url: str
    group_roles: Mapping[str, str]
    client_id: str = ""
    organisation: str = ""
    service_clients: tuple[str, ...] = ()
    key_cache_ttl: timedelta = DEFAULT_KEY_CACHE_TTL


@dataclass(frozen=True)
class WorkerConfig:
    """The client background work obtains its own credential as, when it has one.

    `auth-integration`: *"Work performed with no live human caller SHALL
    authenticate with a service credential, SHALL resolve to an actor identified
    as automation"*. That credential is minted by a client-credentials exchange,
    and these two are the client it is minted for.

    Optional as a **pair**, and the pair is why :attr:`available` exists: an id
    with no secret cannot obtain anything, so half a configuration behaves like
    the absence it is rather than failing once per scheduled run. A deployment
    that configures neither still validates, still writes back and is still
    recorded as automation — it simply has no token to present to anything that
    asks for one.

    :attr:`secret` is a :class:`Secret`, so it is kept out of every log line,
    refusal and traceback exactly as `CANON_REPOSITORY_CREDENTIAL` is.
    """

    client_id: str = ""
    secret: Secret = Secret("")

    @property
    def available(self) -> bool:
        """Whether background work can obtain a credential of its own."""
        return bool(self.client_id and self.secret)

    @property
    def absence(self) -> str:
        """Why it cannot, for a caller that has to say so."""
        if not self.client_id and not self.secret:
            return f"{WORKER_CLIENT_ID} and {WORKER_CLIENT_SECRET} are not set"
        return f"{WORKER_CLIENT_ID} and {WORKER_CLIENT_SECRET} are not both set"


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


WORKER_ADMISSION = (
    "a deployment that names the client its background work signs in as must also "
    "admit that client as automation, or its own worker is refused by its own "
    "verifier and the scheduled pass is recorded as unattributed automation"
)
"""The sentence a half-configured worker earns, and why it is a refusal.

The degradation this prevents is quiet, which is the whole argument for making
it loud. A worker refused by its own API keeps running: the scheduled pass still
fetches, still validates, still records — just as plain `automation` rather than
as the client somebody registered for it. Nothing fails, nothing pages, and the
attribution is wrong in a journal nobody reads until they need it.
"""


def worker_admission_problems(worker: str, admitted: Sequence[str]) -> tuple[Problem, ...]:
    """The refusal a worker nobody admits earns, naming both variables.

    Both, for the same reason :func:`rollover_problems` names both: either one
    could be the one that is wrong, and the person reading knows which. A
    deployment that configures no worker at all is not a mismatch — it has no
    background client, which is an ordinary and supported shape.
    """
    if not worker or worker in admitted:
        return ()
    listed = ", ".join(admitted) if admitted else "nothing"
    return (
        Problem(
            WORKER_CLIENT_ID,
            f"not listed in {AUTH_SERVICE_CLIENTS}: {WORKER_ADMISSION}",
            present=True,
        ),
        Problem(
            AUTH_SERVICE_CLIENTS,
            f"lists {listed}, not {worker!r}: {WORKER_ADMISSION}",
            present=True,
        ),
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
class BrowserAccess:
    """Which browser origins may read this API, and nothing wider.

    `deploy/coolify.yaml` puts the API on `api.backend…` and the application on
    `canon.backend…`, so every request the web application makes is
    cross-origin: without this the browser refuses the response it already
    received, and the application shows an unavailable state against a service
    that is perfectly healthy.

    Empty is the honest default. A deployment that has not been told which
    application talks to it sends no cross-origin permission at all, which is
    what a service reached only by the command line and the agent surface should
    do — and it is why this is a configured list and never a wildcard.
    """

    origins: tuple[str, ...] = ()

    @property
    def permitted(self) -> bool:
        return bool(self.origins)


@dataclass(frozen=True)
class ServiceConfiguration:
    """Everything the hosted service needs, already read and already checked."""

    repository: RepositoryConfig
    identity: IdentityConfig
    storage: StorageConfig
    rollover: RolloverConfig
    worker: WorkerConfig = WorkerConfig()
    model: ModelConfig = ModelConfig()
    browser: BrowserAccess = BrowserAccess()


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
    problems = rollover_problems(rollover) + worker_admission_problems(
        values[WORKER_CLIENT_ID], values[AUTH_SERVICE_CLIENTS]
    )
    if problems:
        raise refusal(problems)
    return ServiceConfiguration(
        repository=RepositoryConfig(
            url=values[REPOSITORY_URL],
            branch=values[REPOSITORY_BRANCH],
            credential=Secret(values[REPOSITORY_CREDENTIAL]),
            fetch_interval=values[FETCH_INTERVAL],
            webhook_secret=Secret(values[WEBHOOK_SECRET]),
            project=values[PROJECT],
            working_copies=values[WORKING_COPIES] or DEFAULT_WORKING_COPIES,
        ),
        identity=IdentityConfig(
            issuer=values[AUTH_ISSUER],
            audience=values[AUTH_AUDIENCE],
            key_set_url=values[AUTH_KEY_SET_URL],
            group_roles=values[GROUP_ROLES],
            client_id=values[AUTH_CLIENT_ID],
            organisation=values[AUTH_ORG_ID],
            service_clients=tuple(values[AUTH_SERVICE_CLIENTS] or ()),
            key_cache_ttl=values[AUTH_KEY_CACHE_TTL] or DEFAULT_KEY_CACHE_TTL,
        ),
        worker=WorkerConfig(
            client_id=values[WORKER_CLIENT_ID],
            secret=Secret(values[WORKER_CLIENT_SECRET]),
        ),
        storage=StorageConfig(
            database_url=Secret(values[DATABASE_URL]),
            object_store_url=values[OBJECT_STORE_URL],
            link_expiry=values[LINK_EXPIRY],
        ),
        rollover=rollover,
        browser=BrowserAccess(origins=tuple(values[WEB_ORIGINS] or ())),
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
    "DEFAULT_WORKING_COPIES",
    "GROUP_SEPARATOR",
    "OPTIONAL",
    "PAIR_SEPARATOR",
    "PREFIX",
    "REQUIRED",
    "ROLLOVER_ORDER",
    "SECRETS",
    "SETTINGS",
    "WEB_ORIGINS",
    "WILDCARD",
    "WORKING_COPIES",
    "BrowserAccess",
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
    "WorkerConfig",
    "client_ids",
    "group_roles",
    "load",
    "missing_from",
    "origins",
    "read",
    "refusal",
    "rollover_problems",
]
