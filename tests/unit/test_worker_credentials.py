"""Background work authenticates as itself, and its secret never prints.

`auth-integration`: *"Work performed with no live human caller SHALL
authenticate with a service credential, SHALL resolve to an actor identified as
automation, SHALL be recorded as automation rather than as any person, and SHALL
be refused every operation the project reserves to a person."* The second half
has always been true here; the first half had **no configuration behind it** —
`CANON_WORKER_CLIENT_ID` and `CANON_WORKER_CLIENT_SECRET` did not exist, so
there was no client for a scheduled run to be.

What this suite pins down is the shape of that wiring rather than the exchange
itself (`tests/integration/test_auth_flows.py` drives a real client-credentials
exchange against a real issuer):

* the pair is **optional and is a pair**, so half of it behaves like the absence
  instead of failing once per scheduled run;
* nothing is obtained at build time, because a boot that needed the identity
  service to be up is the cascade D8 exists to prevent;
* an unreachable issuer degrades to `automation` rather than stopping background
  validation — an outage must not become a growing backlog of unvalidated
  exports;
* a resolution that is **not** automation is refused, so this path can never
  record a pass as a person however it was configured;
* the secret is a
  :class:`~cybercanon.adapters.wiring.configuration.Secret` everywhere, so it
  cannot reach a log line, a refusal or a traceback — the treatment
  `CANON_REPOSITORY_CREDENTIAL` gets, and for the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import pytest

from cybercanon.adapters.outbound.auth.flows import Endpoints
from cybercanon.adapters.wiring.configuration import (
    IdentityConfig,
    RepositoryConfig,
    RolloverConfig,
    Secret,
    ServiceConfiguration,
    StorageConfig,
    WorkerConfig,
)
from cybercanon.adapters.wiring.identity import background_identity, worker_credentials
from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityServiceUnavailable,
    ResolvedIdentity,
)
from cybercanon.domain.identity import Actor, ActorId, automation_actor
from cybercanon.domain.validation_outcome import AUTOMATION

pytestmark = pytest.mark.unit

SECRET = "the-worker-clients-secret"  # not-a-credential: invented for this suite
CLIENT = "cyb_Worker00Client01"
TOKEN = "a-service-credential"
ENDPOINT = "https://auth.example/api/v1/auth/oauth2/token"


def configured(**worker: Any) -> ServiceConfiguration:
    """A deployment, with whatever the scenario says about the worker client."""
    return ServiceConfiguration(
        repository=RepositoryConfig(
            url="git@github.com:cyberdynecorp/ronin.git",
            branch="canon",
            credential=Secret("a-deploy-key"),  # not-a-credential
            fetch_interval=timedelta(minutes=5),
            webhook_secret=Secret("a-webhook-secret"),  # not-a-credential
            project="ronin",
        ),
        identity=IdentityConfig(
            issuer="https://auth.example",
            audience="cybercanon",
            key_set_url="https://auth.example/.well-known/jwks.json",
            group_roles={"artist": "ARTIST"},
            client_id="cyb_Deploy000Client1",
            organisation="org_Worker000Studio",
        ),
        storage=StorageConfig(
            database_url=Secret("postgresql://canon@db/canon"),
            object_store_url="https://minio.example",
            link_expiry=timedelta(minutes=2),
        ),
        rollover=RolloverConfig(
            write_back_timeout=timedelta(seconds=30), drain_window=timedelta(seconds=90)
        ),
        worker=WorkerConfig(**worker),
    )


class Exchanging:
    """The issuer's token endpoint, as a transport that counts and can refuse."""

    def __init__(self, *, refuses: bool = False) -> None:
        self.refuses = refuses
        self.posted: list[tuple[str, Mapping[str, str]]] = []

    def post(self, url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        self.posted.append((url, dict(form)))
        if self.refuses:
            raise OSError("the identity service is not answering")
        return {"access_token": TOKEN, "token_type": "Bearer", "expires_in": 3600}


class Resolving:
    """An identity provider that answers with whatever this scenario resolved."""

    def __init__(self, actor: Actor | None = None, *, unavailable: bool = False) -> None:
        self.actor = actor if actor is not None else automation_actor(identifier="client:worker")
        self.unavailable = unavailable
        self.resolutions = 0

    def resolve(self, credential: Credential) -> ResolvedIdentity:
        self.resolutions += 1
        if self.unavailable:
            raise IdentityServiceUnavailable("the identity service")
        return ResolvedIdentity(actor=self.actor)


# --------------------------------------------------------------------------
# The pair, and what half of it means
# --------------------------------------------------------------------------


def test_a_deployment_with_no_worker_client_obtains_nothing() -> None:
    assert worker_credentials(configured()) is None


@pytest.mark.parametrize(
    "worker",
    [{"client_id": CLIENT}, {"secret": Secret(SECRET)}],
    ids=["an id with no secret", "a secret with no id"],
)
def test_half_a_pair_behaves_like_the_absence_it_is(worker: dict[str, Any]) -> None:
    """Failing once per scheduled run would be the other, worse option."""
    assert worker_credentials(configured(**worker)) is None


def test_a_configured_pair_produces_a_flow_that_has_obtained_nothing_yet() -> None:
    """Building the deployment must not need the identity service to be up."""
    transport = Exchanging()

    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)), transport=transport
    )

    assert credentials is not None
    assert transport.posted == [], "a boot that talked to the issuer is the cascade D8 forbids"


def test_the_exchange_is_a_client_credentials_grant_at_the_discovered_endpoint() -> None:
    transport = Exchanging()
    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)),
        endpoints=_pinned(),
        transport=transport,
    )
    assert credentials is not None

    credentials.obtain()

    url, form = transport.posted[0]
    assert url == ENDPOINT
    assert form["grant_type"] == "client_credentials"
    assert form["client_id"] == CLIENT


# --------------------------------------------------------------------------
# What a pass is recorded as
# --------------------------------------------------------------------------


def test_with_no_credential_a_pass_is_recorded_as_automation() -> None:
    """Exactly what it was before there was a client to be, and deliberately so."""
    assert background_identity(None, provider=None)() == AUTOMATION


def test_a_resolved_service_credential_names_the_client_it_was_minted_for() -> None:
    transport = Exchanging()
    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)),
        endpoints=_pinned(),
        transport=transport,
    )
    provider = Resolving(automation_actor(identifier=f"client:{CLIENT}"))

    assert background_identity(credentials, provider=provider)() == f"client:{CLIENT}"


def test_the_credential_is_obtained_once_and_then_remembered() -> None:
    transport = Exchanging()
    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)),
        endpoints=_pinned(),
        transport=transport,
    )
    provider = Resolving()
    attributed_to = background_identity(credentials, provider=provider)

    attributed_to()
    attributed_to()

    assert len(transport.posted) == 1
    assert provider.resolutions == 1


def test_an_unreachable_issuer_does_not_stop_background_work() -> None:
    """An outage must not turn into a backlog of unvalidated exports."""
    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)),
        endpoints=_pinned(),
        transport=Exchanging(refuses=True),
    )

    assert background_identity(credentials, provider=Resolving())() == AUTOMATION


def test_an_outage_is_retried_at_the_next_pass_rather_than_remembered() -> None:
    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)),
        endpoints=_pinned(),
        transport=Exchanging(),
    )
    provider = Resolving(unavailable=True)
    attributed_to = background_identity(credentials, provider=provider)

    assert attributed_to() == AUTOMATION
    provider.unavailable = False

    assert attributed_to() != AUTOMATION
    assert provider.resolutions == 2


def test_a_credential_resolving_to_a_person_is_refused() -> None:
    """However it was configured, this path can never record a pass as somebody."""
    credentials = worker_credentials(
        configured(client_id=CLIENT, secret=Secret(SECRET)),
        endpoints=_pinned(),
        transport=Exchanging(),
    )
    person = Actor(id=ActorId("auth|rafa"), display_name="auth|rafa")

    assert background_identity(credentials, provider=Resolving(person))() == AUTOMATION


# --------------------------------------------------------------------------
# The secret
# --------------------------------------------------------------------------


def test_the_secret_never_renders_itself() -> None:
    """Not in `repr`, not in `str`, and therefore not in a log line or traceback."""
    worker = WorkerConfig(client_id=CLIENT, secret=Secret(SECRET))

    assert (
        SECRET not in f"{worker!r} {worker} {configured(client_id=CLIENT, secret=Secret(SECRET))}"
    )


def test_the_absence_names_the_two_variables_and_quotes_neither_value() -> None:
    absent = WorkerConfig()

    assert "CANON_WORKER_CLIENT_ID" in absent.absence
    assert "CANON_WORKER_CLIENT_SECRET" in absent.absence


def _pinned() -> Endpoints:
    """The token endpoint, written down, so no suite here reads a document."""
    return Endpoints(token=ENDPOINT)
