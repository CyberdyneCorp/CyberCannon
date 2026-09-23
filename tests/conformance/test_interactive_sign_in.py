"""Task 2.1 — the device authorization flow, fake and real adapter.

The real one runs against `tools/canon_issuer`'s in-process CyberdyneAuth rather
than a socket: it signs with cached RSA keys and answers the device-code and
token endpoints, so the whole flow is exercised — grant, poll, credential — at
the cost of a function call. A suite that pointed at a real issuer would either
need a network or would not run, and a conformance suite that does not run is
the same failure as a fake that lies.

The value is the asymmetry the layer exists for: the sign-in the write surface
depends on is the *fake* in every unit test and BDD step, and this is what says
the fake behaves like the thing it stands in for.
"""

from __future__ import annotations

from pathlib import Path

from contract import implementation_fixture
from interactive_sign_in_contract import InteractiveSignInContract

from canon_issuer import AUTHORIZE_PATH, DEVICE_CODE_PATH, TOKEN_PATH, FakeIssuer
from cybercanon.adapters.outbound.auth.flows import DeviceAuthorization, Endpoints
from cybercanon.application.ports.interactive_sign_in import DeviceGrant, InteractiveSignIn
from cybercanon.application.testing.interactive_sign_in import InMemoryInteractiveSignIn


def in_memory(directory: Path) -> InMemoryInteractiveSignIn:
    return InMemoryInteractiveSignIn()


def device_authorization(directory: Path) -> DeviceAuthorization:
    issuer = FakeIssuer()
    flow = DeviceAuthorization(
        endpoints=Endpoints(
            token=f"{issuer.issuer}{TOKEN_PATH}",
            device_authorization=f"{issuer.issuer}{DEVICE_CODE_PATH}",
            authorization=f"{issuer.issuer}{AUTHORIZE_PATH}",
        ),
        client_id=issuer.client_id,
        transport=issuer,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
    )
    flow.issuer = issuer  # type: ignore[attr-defined]
    return flow


implementation = implementation_fixture(fake=in_memory, device=device_authorization)


class TestInteractiveSignIn(InteractiveSignInContract):
    """The device authorization contract, against both implementations."""

    def approve(self, implementation: InteractiveSignIn, grant: DeviceGrant) -> None:
        """The real issuer needs the person's click; the fake has already agreed."""
        issuer = getattr(implementation, "issuer", None)
        if issuer is not None:
            issuer.approve(grant.user_code)
