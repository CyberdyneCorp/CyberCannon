"""What every `IdentityProvider` SHALL do, whoever implements it (tasks 2.1, 4.5).

The corpus is three credentials, and the third is the interesting one: a
provider MAY describe the git authorship of the person it resolved, and MAY NOT.
Both are conforming, and D13's precedence — provider claims, then the mapping
file — is only meaningful because the port permits both. So the contract seeds
one of each and asserts that "no emails" comes back as an empty tuple rather
than as a failure or a `None` some call site has to handle.

The permission is *per provider* as well as per person, which is why there are
three fixtures. `implementation` is every provider there is, and runs everything
that is true whoever answered. `describes_git_authorship` is a provider that
supplies commit addresses where it knows them, and `without_git_authorship` is
one that never supplies them at all — CyberdyneAuth as it stands today, because
a real access token carries no `git_emails` claim, no `email` and no `name`. The
two authorship shapes are asserted against the fixture that can actually be
*asked*: a suite that demanded commit addresses of every implementation would be
demanding a claim the issuer does not send, which is how the version of this
file that minted one came to agree with the adapter for ever.

The resolved person is asserted to be the same either way: D13 decides where the
emails come from, never who the actor is.

**The person the contract expects is described only by what a provider can
really answer.** There is no display name here beyond the subject and no
authorship on the actor, because the identity service supplies neither: a
contract that expected a name would be satisfiable only by a fixture that
invented one.

The failure side is contract too: an unresolvable credential raises
:class:`IdentityUnavailable` and never returns a partial actor, because the
resolution chain distinguishes "the provider declined" from "the provider
answered" and a half-answer would collapse the two.
"""

from __future__ import annotations

import pytest

from cybercanon.application.ports.identity_provider import (
    Credential,
    IdentityProvider,
    IdentityUnavailable,
)
from cybercanon.domain.identity import Actor, ActorId, Role
from cybercanon.domain.tenancy import Tenant

PROJECT = "cyberdyne-game"

ORGANISATION = "org_C0ntract0Studio"
"""The organisation both people belong to and the deployment serves. **Invented.**

A person reads `PROJECT` because they are a member of this organisation and hold
a role on this deployment's client. The identifier is the contract's own, named
after nothing: an organisation id in this repository would tie the suite to a
record in somebody else's database.
"""

DESCRIBED = Credential("token-rafa-with-emails")
"""A credential whose provider also supplies the person's commit addresses."""

BARE = Credential("token-ana-without-emails")
"""A credential resolved without git authorship — the ordinary case today."""

UNKNOWN = Credential("token-nobody-ever-issued")

RAFA = Actor(
    id=ActorId("auth|rafa"),
    display_name="auth|rafa",
    roles=(Role.ARTIST,),
    projects=(PROJECT,),
    tenant=Tenant(ORGANISATION),
)
"""One resolved person, described by the four things a provider really answers.

The display name is the subject, because an access token carries no `name`: a
person's readable name is the web application's to fetch and the actors mapping's
to record, and an actor that carried an invented one would be the fixture
describing somebody the identity service cannot.
"""

RAFA_EMAILS = ("rafa@cyberdyne.com", "rafa@personal.dev")

ANA = Actor(
    id=ActorId("auth|ana"),
    display_name="auth|ana",
    roles=(Role.ART_DIRECTOR,),
    projects=(PROJECT,),
    tenant=Tenant(ORGANISATION),
)


class IdentityProviderContract:
    """The behaviour every identity provider shares."""

    def test_a_credential_resolves_to_its_actor(self, implementation: IdentityProvider) -> None:
        resolved = implementation.resolve(DESCRIBED)

        assert resolved.actor == RAFA

    def test_a_provider_may_supply_git_author_emails(
        self, describes_git_authorship: IdentityProvider
    ) -> None:
        """D13's first link: when the provider knows, the mapping file is not needed.

        Asked of the providers that describe authorship, because the permission
        is per provider: CyberdyneAuth describes none — its token carries no
        `git_emails` claim — and the scenario below is the half of the port it
        answers.
        """
        resolved = describes_git_authorship.resolve(DESCRIBED)

        assert resolved.git_emails == RAFA_EMAILS
        assert resolved.describes_git_authorship

    def test_a_provider_may_supply_none_and_that_is_an_empty_tuple(
        self, implementation: IdentityProvider
    ) -> None:
        resolved = implementation.resolve(BARE)

        assert resolved.actor == ANA
        assert resolved.git_emails == ()
        assert not resolved.describes_git_authorship

    def test_resolution_is_stable(self, implementation: IdentityProvider) -> None:
        """Two resolutions of one credential are the same person, not two."""
        assert implementation.resolve(BARE) == implementation.resolve(BARE)

    def test_the_actor_carries_roles_the_domain_can_decide_from(
        self, implementation: IdentityProvider
    ) -> None:
        """No claim, group or token field crosses the boundary — only roles."""
        resolved = implementation.resolve(DESCRIBED)

        assert resolved.actor.holds(Role.ARTIST)
        assert resolved.actor.may_see(PROJECT)

    def test_an_unresolvable_credential_is_a_named_failure(
        self, implementation: IdentityProvider
    ) -> None:
        with pytest.raises(IdentityUnavailable):
            implementation.resolve(UNKNOWN)

    def test_a_credential_never_prints_itself(self, implementation: IdentityProvider) -> None:
        """The secret must not reach a log line, a prose response or a traceback."""
        assert DESCRIBED.value not in f"{DESCRIBED!r} {DESCRIBED}"

    # -- a provider that describes no git authorship at all (task 4.5) ----

    def test_a_provider_may_describe_no_git_authorship_at_all(
        self, without_git_authorship: IdentityProvider
    ) -> None:
        """The ordinary case today: the mapping file answers instead (D13)."""
        resolved = without_git_authorship.resolve(DESCRIBED)

        assert resolved.actor == RAFA
        assert resolved.git_emails == ()
        assert not resolved.describes_git_authorship

    def test_a_provider_that_describes_none_still_resolves_the_same_person(
        self, implementation: IdentityProvider, without_git_authorship: IdentityProvider
    ) -> None:
        """Authorship is what differs between the two; the actor never is."""
        described = implementation.resolve(DESCRIBED)
        bare = without_git_authorship.resolve(DESCRIBED)

        assert bare.actor == described.actor
        assert bare.actor.holds(Role.ARTIST)

    def test_a_provider_that_describes_none_still_fails_by_name(
        self, without_git_authorship: IdentityProvider
    ) -> None:
        with pytest.raises(IdentityUnavailable):
            without_git_authorship.resolve(UNKNOWN)
