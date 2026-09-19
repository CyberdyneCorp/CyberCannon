"""What every `CredentialStore` SHALL do, whoever implements it (task 8.6).

Three operations and one prohibition, and the prohibition is the reason this
contract exists at all: *"[the credential] SHALL NOT be written into the
repository or any file inside it."* A conformance suite cannot prove a negative
about the whole file system, but it can prove the one thing that makes the
negative achievable — **the port has no way to be told where to put anything**.
So the contract exercises a store it was handed and never names a location, and
the suite that runs it stages a repository beside each implementation and
asserts the working tree is untouched.

The rest is the behaviour every implementation shares:

* an absent credential is ``None`` and never a failure, because a machine that
  has never signed in is the machine `canon validate` is built for;
* storing twice replaces rather than accumulates — one machine, one person;
* erasing answers whether there was anything, and erasing twice is not an error:
  the intent is *no credential here*, and it is satisfied both times;
* what comes back out is what went in, compared as a
  :class:`~cybercanon.application.ports.identity_provider.Credential` — which
  also asserts the value survives a round trip through a store that may have had
  to encode it.
"""

from __future__ import annotations

from cybercanon.application.ports.credential_store import CredentialStore
from cybercanon.application.ports.identity_provider import Credential

ISSUED = Credential("an-issuer-signed-credential.for.this.person")
REISSUED = Credential("a-second-credential.after.signing.in.again")


class CredentialStoreContract:
    """The behaviour every credential store shares."""

    def test_nothing_is_stored_until_something_is(self, implementation: CredentialStore) -> None:
        """A machine that has never signed in answers, rather than failing."""
        assert implementation.load() is None

    def test_what_is_stored_comes_back(self, implementation: CredentialStore) -> None:
        implementation.store(ISSUED)

        assert implementation.load() == ISSUED

    def test_storing_again_replaces(self, implementation: CredentialStore) -> None:
        """One machine signs in as one person; a second sign-in is not a second slot."""
        implementation.store(ISSUED)
        implementation.store(REISSUED)

        assert implementation.load() == REISSUED

    def test_erasing_removes_it_and_says_so(self, implementation: CredentialStore) -> None:
        implementation.store(ISSUED)

        assert implementation.erase() is True
        assert implementation.load() is None

    def test_erasing_nothing_is_not_an_error(self, implementation: CredentialStore) -> None:
        """Signing out twice satisfies the intent twice."""
        assert implementation.erase() is False
        assert implementation.erase() is False

    def test_a_stored_credential_never_prints_itself(self, implementation: CredentialStore) -> None:
        """The value must not reach a log line by way of the store's own repr."""
        implementation.store(ISSUED)
        loaded = implementation.load()

        assert loaded is not None
        assert ISSUED.value not in f"{implementation!r} {loaded!r} {loaded}"

    def test_the_port_offers_no_location(self, implementation: CredentialStore) -> None:
        """No operation takes a path, so none can be pointed at a working copy."""
        for name in ("store", "load", "erase"):
            operation = getattr(implementation, name)
            annotations = getattr(operation, "__annotations__", {})
            assert not any("Path" in str(kind) for kind in annotations.values()), name
