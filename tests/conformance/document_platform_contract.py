"""What every `DocumentPlatform` SHALL do, whoever implements it (task 2.1, 2.2).

The port is `add-cyberarche-integration`'s D2 boundary, and the contract asserts
exactly the properties the application depends on:

* **one answer per reference, in order**, each carrying its own state — which is
  what makes *"one broken link does not break the list"* possible at all;
* **a forbidden reference discloses nothing** — no title, no summary. An
  implementation that returned the title and left it to the card type to clear
  would pass every caller test and leak to anything that read the port directly;
* **a deleted document is `MISSING`, not forbidden and not unreachable**;
* **the credential is per call**, so two different callers get two different
  answers from the same instance;
* **creation is refused by name** when the platform says this person may not,
  and nothing is created;
* **the history is read, never kept** — newest first, and empty rather than
  raising when the document is not readable.

And one structural assertion that is the whole of D2: **no implementation holds
a credential as construction state.** A service token in an adapter would make
every call silently run as the service, and this is the check that makes that
impossible to add quietly rather than merely discouraged.
"""

from __future__ import annotations

import inspect
from datetime import timedelta

import pytest

from cybercanon.application.ports.document_platform import (
    NO_CREDENTIAL,
    Credential,
    DocumentCreationRefused,
    PlatformUnavailable,
    UnavailabilityReason,
)
from cybercanon.domain.documents import DocumentRef, DocumentState

WORKSPACE = "w_production"

READABLE = "d_readable"
FORBIDDEN = "d_forbidden"
DELETED = "d_deleted"
ABSENT = "d_absent"

READABLE_TITLE = "mech_scout — design rationale"
READABLE_BODY = "the scout reads as a courier because the faction is logistics"

RAFA = "token-rafa"
BRUNO = "token-bruno"

CREDENTIAL_NAMES = ("token", "credential", "bearer", "secret", "password", "authorization", "jwt")
"""Names a held credential would plausibly go by. D2 forbids all of them."""


def a_ref(document_id: str, workspace: str = WORKSPACE) -> DocumentRef:
    return DocumentRef(
        workspace=workspace,
        document_id=document_id,
        url=f"https://documents.invalid/w/{workspace}/d/{document_id}",
    )


class DocumentPlatformContract:
    """The contract, run against the fake and against every real adapter."""

    # -- D2: whose authority is this ------------------------------------

    def test_no_credential_is_held_as_construction_state(self, implementation) -> None:
        """Task 2.1: the adapter cannot have a token, so no call can run as one."""
        parameters = set(inspect.signature(type(implementation).__init__).parameters)
        attributes = set(vars(implementation))
        for name in CREDENTIAL_NAMES:
            assert not any(name in parameter for parameter in parameters), (
                f"{type(implementation).__name__}.__init__ takes {name!r}: a credential "
                "belongs on every call, never on the constructor (D2)"
            )
            assert not any(name in attribute for attribute in attributes), (
                f"{type(implementation).__name__} holds {name!r} as state (D2)"
            )

    def test_every_method_takes_the_caller_s_credential(self, implementation) -> None:
        for name in ("resolve", "create", "search", "revisions"):
            parameters = inspect.signature(getattr(implementation, name)).parameters
            assert "credential" in parameters, f"{name} decides nothing about authority"

    def test_two_callers_of_one_instance_get_their_own_answers(self, implementation) -> None:
        """The same reference, two people, two states. One instance, no reconstruction."""
        ref = a_ref(READABLE)

        mine = implementation.resolve((ref,), Credential(RAFA))[0]
        theirs = implementation.resolve((ref,), Credential(BRUNO))[0]

        assert mine.state is DocumentState.READABLE
        assert theirs.state is DocumentState.FORBIDDEN

    def test_an_absent_credential_is_refused_rather_than_served_anonymously(
        self, implementation
    ) -> None:
        with pytest.raises(PlatformUnavailable) as refusal:
            implementation.resolve((a_ref(READABLE),), NO_CREDENTIAL)

        assert refusal.value.reason is UnavailabilityReason.REJECTED

    # -- resolution -----------------------------------------------------

    def test_one_answer_per_reference_in_the_order_asked(self, implementation) -> None:
        refs = (a_ref(READABLE), a_ref(FORBIDDEN), a_ref(DELETED))

        answers = implementation.resolve(refs, Credential(RAFA))

        assert len(answers) == len(refs)
        assert [answer.document_id for answer in answers] == [ref.document_id for ref in refs]

    def test_a_readable_reference_resolves_to_its_current_title(self, implementation) -> None:
        answer = implementation.resolve((a_ref(READABLE),), Credential(RAFA))[0]

        assert answer.state is DocumentState.READABLE
        assert answer.title == READABLE_TITLE

    def test_a_forbidden_reference_discloses_no_title_and_no_summary(self, implementation) -> None:
        answer = implementation.resolve((a_ref(FORBIDDEN),), Credential(RAFA))[0]

        assert answer.state is DocumentState.FORBIDDEN
        assert answer.title == ""
        assert answer.summary == ""

    def test_the_three_failures_are_distinguishable(self, implementation) -> None:
        """Deleted, forbidden and never-existed are three answers, not one."""
        states = {
            ref.document_id: answer.state
            for ref, answer in zip(
                (a_ref(DELETED), a_ref(FORBIDDEN), a_ref(ABSENT)),
                implementation.resolve(
                    (a_ref(DELETED), a_ref(FORBIDDEN), a_ref(ABSENT)), Credential(RAFA)
                ),
                strict=True,
            )
        }

        assert states[DELETED] is DocumentState.MISSING
        assert states[FORBIDDEN] is DocumentState.FORBIDDEN
        assert states[ABSENT] is DocumentState.MISSING

    def test_one_unreadable_reference_does_not_hide_a_readable_one(self, implementation) -> None:
        answers = implementation.resolve((a_ref(FORBIDDEN), a_ref(READABLE)), Credential(RAFA))

        assert answers[0].state is DocumentState.FORBIDDEN
        assert answers[1].title == READABLE_TITLE

    def test_resolving_nothing_asks_nothing_and_answers_nothing(self, implementation) -> None:
        assert implementation.resolve((), Credential(RAFA)) == ()

    # -- creation, the only write (D10) ---------------------------------

    def test_creating_a_document_yields_an_openable_reference(self, implementation) -> None:
        created = implementation.create(WORKSPACE, "mech_scout — design document", Credential(RAFA))

        assert created.workspace == WORKSPACE
        assert created.document_id
        assert created.url.startswith("http")
        assert created.title == "mech_scout — design document"

    def test_a_created_document_resolves_under_the_title_it_was_given(self, implementation) -> None:
        created = implementation.create(WORKSPACE, "a fresh document", Credential(RAFA))

        answer = implementation.resolve((a_ref(created.document_id),), Credential(RAFA))[0]

        assert answer.state is DocumentState.READABLE
        assert answer.title == "a fresh document"

    def test_a_creation_the_platform_refuses_is_named_rather_than_silent(
        self, implementation
    ) -> None:
        with pytest.raises(DocumentCreationRefused) as refusal:
            implementation.create(WORKSPACE, "not mine to make", Credential(BRUNO))

        assert WORKSPACE in str(refusal.value)

    # -- the platform's own history, read (never copied) ----------------

    def test_a_readable_document_s_revisions_come_back_newest_first(self, implementation) -> None:
        revisions = implementation.revisions(a_ref(READABLE), Credential(RAFA))

        assert len(revisions) >= 2
        assert [revision.seq for revision in revisions] == sorted(
            (revision.seq for revision in revisions), reverse=True
        )

    def test_an_unreadable_document_has_no_listable_history(self, implementation) -> None:
        assert implementation.revisions(a_ref(FORBIDDEN), Credential(RAFA)) == ()
        assert implementation.revisions(a_ref(ABSENT), Credential(RAFA)) == ()

    def test_a_revision_carries_metadata_and_no_content(self, implementation) -> None:
        """The history is linked to, not kept: there is no member that could hold a body."""
        revision = implementation.revisions(a_ref(READABLE), Credential(RAFA))[0]

        assert set(type(revision).__dataclass_fields__) == {"id", "seq", "created_at", "label"}

    # -- delegated search ------------------------------------------------

    def test_search_returns_passages_that_name_their_source_document(self, implementation) -> None:
        passages = implementation.search(
            "courier", Credential(RAFA), timedelta(seconds=5), WORKSPACE
        )

        assert passages
        assert all(passage.document_id for passage in passages)
        assert all(passage.url.startswith("http") for passage in passages)

    def test_search_never_returns_a_document_this_caller_may_not_read(self, implementation) -> None:
        passages = implementation.search(
            "courier", Credential(BRUNO), timedelta(seconds=5), WORKSPACE
        )

        assert all(passage.document_id != READABLE for passage in passages)

    def test_a_passage_carries_no_ordering_value(self, implementation) -> None:
        """D6: there is nothing here an exact result could be compared against."""
        passage = implementation.search(
            "courier", Credential(RAFA), timedelta(seconds=5), WORKSPACE
        )[0]

        assert set(type(passage).__dataclass_fields__) == {
            "workspace",
            "document_id",
            "title",
            "url",
            "text",
        }

    # -- the boundary the port exists to keep (D9, D10) -----------------

    def test_the_port_has_no_method_that_returns_a_document_body(self, implementation) -> None:
        forbidden = {"body", "content", "blocks", "read", "fetch", "download", "export"}
        public = {
            name
            for name in dir(implementation)
            if not name.startswith("_") and callable(getattr(implementation, name))
        }

        assert not public & forbidden, f"{sorted(public & forbidden)} would reopen D9"
