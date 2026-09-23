"""What every device authorization flow SHALL do, whoever implements it (2.1).

`InteractiveSignIn` is the `DeviceAuthorizationFlow` the write surface needs,
and the contract is mostly a set of absences, because the requirement is:
*"the person is shown a code and a URL, completes authentication in a browser,
and the process obtains the credential without the person ever pasting a secret
into a terminal or a configuration file."*

So the contract asserts, in order:

* a grant carries **what a person is shown** — an address and a code — and a
  handle the issuer owns;
* the handle **does not print**. It is a bearer value for the life of the grant,
  and a handle in a log line is a sign-in somebody else can complete;
* the flow **has no slot for a secret**. No method here takes a password, which
  is the structural half of *"SHALL NOT accept a password"*;
* a declined or expired grant is
  :class:`~cybercanon.application.ports.interactive_sign_in.SignInFailed` rather
  than a ``None`` every call site has to remember to test.

`fail_with` and `declines` are the fake's own seeding and are deliberately not
used here: the contract asserts what an implementation *does*, and the two
refusals are exercised where an implementation can actually be made to produce
them.
"""

from __future__ import annotations

import inspect

from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.interactive_sign_in import DeviceGrant, InteractiveSignIn

SECRET_WORDS = ("password", "passphrase", "secret", "token", "pin")


class InteractiveSignInContract:
    """The behaviour every device authorization flow shares.

    :meth:`approve` is the one seam. A real flow waits for a person to click
    something in a browser and a fake does not, so each concrete suite says how
    its implementation is approved; the contract then asserts what happens
    *after* approval without knowing who did the clicking.
    """

    def approve(self, implementation: InteractiveSignIn, grant: DeviceGrant) -> None:
        """The person approves this grant. A fake that always approves does nothing."""

    def test_a_grant_shows_the_person_where_to_go_and_what_to_confirm(
        self, implementation: InteractiveSignIn
    ) -> None:
        grant = implementation.begin()

        assert grant.verification_uri.startswith("http")
        assert grant.user_code.strip()

    def test_a_grant_carries_the_issuer_s_own_handle(
        self, implementation: InteractiveSignIn
    ) -> None:
        assert implementation.begin().device_code.strip()

    def test_a_grant_paces_the_caller(self, implementation: InteractiveSignIn) -> None:
        """Polling honours an interval the issuer chose, so it cannot hammer it."""
        grant = implementation.begin()

        assert grant.interval_s > 0
        assert grant.expires_in_s > 0

    def test_the_handle_never_prints(self, implementation: InteractiveSignIn) -> None:
        grant = implementation.begin()

        assert grant.device_code not in f"{grant!r}"

    def test_an_approved_grant_yields_a_credential(self, implementation: InteractiveSignIn) -> None:
        grant = implementation.begin()
        self.approve(implementation, grant)

        assert isinstance(implementation.redeem(grant), Credential)

    def test_the_credential_never_prints_itself(self, implementation: InteractiveSignIn) -> None:
        grant = implementation.begin()
        self.approve(implementation, grant)
        credential = implementation.redeem(grant)

        assert credential.value not in f"{credential!r} {credential}"

    def test_no_step_of_the_flow_accepts_a_secret(self, implementation: InteractiveSignIn) -> None:
        """*"The surface SHALL NOT accept a password"* — as a shape, not a check."""
        for name in ("begin", "redeem"):
            parameters = inspect.signature(getattr(implementation, name)).parameters
            assert not any(
                word in parameter.lower() for parameter in parameters for word in SECRET_WORDS
            ), name

    def test_a_grant_is_a_value_the_caller_cannot_forge_around(
        self, implementation: InteractiveSignIn
    ) -> None:
        """`redeem` takes the grant `begin` produced, not a caller's own fields."""
        parameters = inspect.signature(implementation.redeem).parameters

        assert len(parameters) == 1
        assert isinstance(implementation.begin(), DeviceGrant)
