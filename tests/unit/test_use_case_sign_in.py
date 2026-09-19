"""Task 8.6 — signing in and out from a terminal, and what never happens.

Three operations, and most of the value is in the negatives, because the
requirement is mostly negative: no password anywhere in the flow, no credential
on any return path, no file written, and a sign-out that works whether or not
there was anything to remove.

The credential never leaving the use case is worth its own test. It would be
natural to return it — the caller just obtained it, after all — and the moment
it is returned it is one `--json` away from standing on standard output, which
is the same class of leak as writing it beside the repository.
"""

from __future__ import annotations

import pytest

from cybercanon.application.ports.credential_store import CredentialStoreUnavailable
from cybercanon.application.ports.identity_provider import Credential
from cybercanon.application.ports.interactive_sign_in import (
    DeviceGrant,
    SignInFailed,
    SignInUnavailable,
)
from cybercanon.application.testing.credential_store import InMemoryCredentialStore
from cybercanon.application.testing.interactive_sign_in import (
    USER_CODE,
    VERIFICATION_URI,
    InMemoryInteractiveSignIn,
)
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.use_cases.sign_in import sign_in, sign_in_status, sign_out

ISSUED = Credential("the-credential-the-issuer-signed")


@pytest.fixture
def store() -> InMemoryCredentialStore:
    return InMemoryCredentialStore()


@pytest.fixture
def flow() -> InMemoryInteractiveSignIn:
    return InMemoryInteractiveSignIn(issues=ISSUED)


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------


def test_an_approved_sign_in_stores_the_credential(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    signed_in = ran(sign_in(interactive_sign_in=flow, credential_store=store))

    assert signed_in.verification_uri == VERIFICATION_URI
    assert store.load() == ISSUED


def test_the_person_is_shown_what_to_approve_while_the_process_waits(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    shown: list[DeviceGrant] = []

    ran(sign_in(interactive_sign_in=flow, credential_store=store, announce=shown.append))

    assert [grant.user_code for grant in shown] == [USER_CODE]


def test_the_credential_is_never_on_a_return_path(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    """A returned credential is one `--json` away from standing on standard output."""
    signed_in = ran(sign_in(interactive_sign_in=flow, credential_store=store))

    assert ISSUED.value not in f"{signed_in!r} {signed_in}"


def test_a_declined_sign_in_stores_nothing(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    flow.declines()

    refusal = refused(sign_in(interactive_sign_in=flow, credential_store=store))

    assert refusal.kind.value == "unauthenticated"
    assert store.load() is None


def test_an_unreachable_issuer_is_unavailable_and_stores_nothing(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    flow.fail_with(SignInUnavailable("the issuer did not answer"))

    refusal = refused(sign_in(interactive_sign_in=flow, credential_store=store))

    assert refusal.kind.value == "unavailable"
    assert store.writes == 0


def test_a_credential_store_that_cannot_be_written_is_reported(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    store.fail_with(CredentialStoreUnavailable("cybercanon", "the keychain is locked"))

    refusal = refused(sign_in(interactive_sign_in=flow, credential_store=store))

    assert refusal.kind.value == "unavailable"


def test_the_sign_in_takes_no_password(flow: InMemoryInteractiveSignIn) -> None:
    """There is no method on the port through which one could be supplied."""
    import inspect

    for operation in (flow.begin, flow.redeem):
        assert not set(inspect.signature(operation).parameters) & {"password", "secret"}


# --------------------------------------------------------------------------
# Signing out, and asking
# --------------------------------------------------------------------------


def test_signing_out_removes_the_credential(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    ran(sign_in(interactive_sign_in=flow, credential_store=store))

    signed_out = ran(sign_out(credential_store=store))

    assert signed_out.removed
    assert store.load() is None


def test_signing_out_twice_is_not_an_error(store: InMemoryCredentialStore) -> None:
    """The intent is *no credential here*, and it is satisfied both times."""
    assert ran(sign_out(credential_store=store)).removed is False
    assert ran(sign_out(credential_store=store)).removed is False


def test_status_says_whether_and_never_what(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    before = ran(sign_in_status(credential_store=store))
    ran(sign_in(interactive_sign_in=flow, credential_store=store))
    after = ran(sign_in_status(credential_store=store))

    assert not before.signed_in
    assert after.signed_in
    assert ISSUED.value not in f"{after!r} {after}"


def test_a_locked_store_is_unavailable_rather_than_signed_out(
    store: InMemoryCredentialStore,
) -> None:
    store.fail_with(CredentialStoreUnavailable("cybercanon", "the keychain is locked"))

    refusal = refused(sign_in_status(credential_store=store))

    assert refusal.kind.value == "unavailable"


def test_a_sign_in_that_never_completes_leaves_nothing_behind(
    flow: InMemoryInteractiveSignIn, store: InMemoryCredentialStore
) -> None:
    flow.fail_with(SignInFailed("the grant expired"))

    refused(sign_in(interactive_sign_in=flow, credential_store=store))

    assert ran(sign_in_status(credential_store=store)).signed_in is False
