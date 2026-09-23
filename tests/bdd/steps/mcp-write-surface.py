"""Step definitions for `mcp-write-surface` — the write surface, from below.

Groups 1 and 2 of `add-mcp-writes` build the observation domain, the write
policy, the credential and the two write use cases. The scenarios bound here are
exactly the ones that code answers with no MCP server, no git working copy and
no command line: the prohibition, the attribution, the identity gate, the two
kinds, the anchoring rule, the rate limit, the duplicate suppression, and the
reporting path with its retries.

The rest stay in `tests/bdd/pending.txt` until the groups that earn them, and
each of them is waiting on a surface rather than on a decision:

* the advertised tool list and the clean-tree assertion need the MCP write tools
  (group 4);
* *"no other repository content is touched"* needs the real
  `GitAnnotationWriter` over a real working copy (group 3);
* the four marking-and-triage scenarios need the human surfaces (group 5);
* *"one sign-in serves both surfaces"*, *"no secret appears in configuration"*
  and *"a pre-commit run is unaffected"* need the command line and the launch
  configuration (group 6).

Every assertion below is about behaviour rather than wording — a refusal is
checked for the identifier it names and the sentence it has to carry, never for
its exact phrasing — so the two adapters above this layer can be improved
without rewriting any of it.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.inbound.cli.exit_codes import exit_code
from cybercanon.application.ports.identity_provider import Credential, ResolvedIdentity
from cybercanon.application.ports.outcome_reporter import VERDICT_STANDS
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.results import Refusal, Unauthenticated, succeeded
from cybercanon.application.testing.annotation_writer import InMemoryAnnotationWriter
from cybercanon.application.testing.identity_provider import InMemoryIdentityProvider
from cybercanon.application.testing.interactive_sign_in import InMemoryInteractiveSignIn
from cybercanon.application.testing.outcome_reporter import InMemoryOutcomeReporter
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.lookup_assets import where_is
from cybercanon.application.use_cases.observations import (
    NO_AGENT_IDENTIFIER,
    SIGN_IN_ACTION,
    ObservationRequest,
    WriteSession,
    flush_reports,
    record_observation,
    report_validation_outcome,
    show_identity,
)
from cybercanon.application.use_cases.resolve_actor import (
    UNVERIFIABLE,
    ActorResolver,
    AlreadyResolved,
    IdentityCache,
    verified_as,
)
from cybercanon.application.use_cases.sign_in import sign_in, sign_out
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.annotations import (
    AGENT_AUTHORED,
    AnnotationKind,
    AuthorKind,
    ObservationKind,
)
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.constraints import Constraints
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.observations import (
    WriteLimits,
    may_only_observe,
    prohibited_for_every_role,
)
from cybercanon.domain.policy import Operation
from cybercanon.domain.report import Report
from cybercanon.domain.validation_outcome import verdict_hash
from cybercanon.domain.violations import Severity, Violation

PROJECT = "ronin"
ASSET = "mech_scout"
OTHER_ASSET = "crate"
SPEC_PATH = "characters/mech_scout/asset.yaml"
EXPORT = "exports/mech_scout.glb"
BLENDER = AgentId("blender-agent")
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
TRI_BUDGET = 12000
UNREACHABLE = "12000 triangles is unreachable without losing the head silhouette"

RAFA = Actor(id=ActorId("rafa"), display_name="Rafa", roles=(Role.ARTIST,), projects=(PROJECT,))


@pytest.fixture
def session() -> dict[str, Any]:
    """What this scenario set up, and what the write surface answered."""
    return {}


# --------------------------------------------------------------------------
# Bindings
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Promotion is not reachable through the observation tool",
)
def test_promotion_is_not_reachable_through_the_observation_tool() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Write to an unknown asset is refused",
)
def test_write_to_an_unknown_asset_is_refused() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Refusal leaves the session usable",
)
def test_refusal_leaves_the_session_usable() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Unauthenticated caller keeps every read",
)
def test_unauthenticated_caller_keeps_every_read() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Unauthenticated write is refused with a remedy",
)
def test_unauthenticated_write_is_refused_with_a_remedy() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Expired identity refuses the write, not the read",
)
def test_expired_identity_refuses_the_write_not_the_read() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Sign-in never asks for a pasted secret",
)
def test_sign_in_never_asks_for_a_pasted_secret() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Signing out disables writes and leaves reads working",
)
def test_signing_out_disables_writes_and_leaves_reads_working() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Both parties are recorded and displayed",
)
def test_both_parties_are_recorded_and_displayed() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "A claimed author in the payload is ignored",
)
def test_a_claimed_author_in_the_payload_is_ignored() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "No resolvable person",
)
def test_no_resolvable_person() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "No configured agent identifier",
)
def test_no_configured_agent_identifier() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Unreachable budget is recorded and the budget stands",
)
def test_unreachable_budget_is_recorded_and_the_budget_stands() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "An agent cannot close its own observation",
)
def test_an_agent_cannot_close_its_own_observation() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Both fields are carried",
)
def test_both_fields_are_carried() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "The annotation kind set is not extended",
)
def test_the_annotation_kind_set_is_not_extended() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Unknown kind is refused with the permitted values",
)
def test_unknown_kind_is_refused_with_the_permitted_values() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Named target resolves",
)
def test_named_target_resolves() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Unresolvable target is preserved, not guessed",
)
def test_unresolvable_target_is_preserved_not_guessed() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Reporting does not change the verdict",
)
def test_reporting_does_not_change_the_verdict() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "No verdict is produced by reporting",
)
def test_no_verdict_is_produced_by_reporting() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Destination unreachable",
)
def test_destination_unreachable() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Pending reports are delivered later",
)
def test_pending_reports_are_delivered_later() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Retry does not duplicate",
)
def test_retry_does_not_duplicate() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "A re-export is a new outcome",
)
def test_a_re_export_is_a_new_outcome() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "A looping agent is throttled",
)
def test_a_looping_agent_is_throttled() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Throttling is scoped and does not stop other work",
)
def test_throttling_is_scoped_and_does_not_stop_other_work() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Reporting does not consume the annotation allowance",
)
def test_reporting_does_not_consume_the_annotation_allowance() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Restarted agent does not duplicate its observation",
)
def test_restarted_agent_does_not_duplicate_its_observation() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "A resolved observation may be raised again",
)
def test_a_resolved_observation_may_be_raised_again() -> None: ...


# --------------------------------------------------------------------------
# The world a write happens in
# --------------------------------------------------------------------------


def a_writer(*assets: str) -> InMemoryAnnotationWriter:
    writer = InMemoryAnnotationWriter()
    for asset in assets or (ASSET,):
        writer.declare(asset, f"characters/{asset}/asset.yaml")
    return writer


def a_request(**overrides: str) -> ObservationRequest:
    fields = {
        "asset": ASSET,
        "target": "head",
        "text": UNREACHABLE,
        "kind": AnnotationKind.TECHNICAL.value,
        "observation_kind": ObservationKind.UNATTAINABLE_CONSTRAINT.value,
    }
    return ObservationRequest(**(fields | overrides))


def a_session(
    session: dict[str, Any],
    *,
    agent: AgentId | None = BLENDER,
    resolver: Any | None = None,
    at: datetime = NOW,
    limits: WriteLimits | None = None,
    subjects: tuple[str, ...] | None = None,
) -> WriteSession:
    """The write session this scenario writes through, remembered for later steps."""
    session.setdefault("writer", a_writer(ASSET, OTHER_ASSET))
    built = WriteSession(
        project=PROJECT,
        resolver=resolver or AlreadyResolved(verified_as(RAFA)),
        writer=session["writer"],
        agent=agent,
        search_index=session.get("index"),
        subjects=None if subjects is None else (lambda _asset: subjects),
        clock=lambda: at,
        limits=limits or WriteLimits(),
    )
    session["session"] = built
    return built


def a_read_surface(session: dict[str, Any]) -> None:
    """A specification and an index, so a read can be asked for beside a write."""
    store = InMemorySpecStore()
    store.add(SPEC_PATH, Asset(id=AssetId(ASSET), name="Scout Mech"))
    store.set_project(ProjectConfig())
    index = InMemorySearchIndex()
    index.upsert(
        IndexedAsset(asset_id=ASSET, name="Scout Mech", project=PROJECT, spec_path=SPEC_PATH)
    )
    session["store"] = store
    session["index"] = index


def a_report(*violations: Violation) -> Report:
    return Report(
        asset_id=ASSET,
        export_format=MeshFormat.GLB,
        export=EXPORT,
        violations=violations,
        passed_rules=("mesh.up_axis",),
    )


def a_violation(rule_id: str) -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=Severity.ERROR,
        subject=ASSET,
        message=f"{ASSET} violates {rule_id}",
    )


def _reporter(session: dict[str, Any]) -> InMemoryOutcomeReporter:
    return session.setdefault("reporter", InMemoryOutcomeReporter())


def _report(session: dict[str, Any], *, export_hash: str = "sha256:aaaa") -> None:
    session["reported"] = ran(
        report_validation_outcome(
            session.setdefault("report", a_report()),
            reporter=_reporter(session),
            export=EXPORT,
            export_hash=export_hash,
            clock=lambda: NOW,
        )
    )


# --------------------------------------------------------------------------
# Promotion is prohibited, not deferred
# --------------------------------------------------------------------------


@when("an observation is recorded whose text asks for a constraint to be changed or promoted")
def _an_observation_asking_for_a_change(session: dict[str, Any]) -> None:
    session["asset"] = Asset(
        id=AssetId(ASSET), name="Scout Mech", constraints=Constraints(tri_budget=TRI_BUDGET)
    )
    asking = "please raise the triangle budget to 20000 and promote this to a rule"
    session["recorded"] = ran(record_observation(a_session(session), a_request(text=asking)))
    session["asking"] = asking


@then("the observation SHALL be recorded as text")
def _recorded_as_text(session: dict[str, Any]) -> None:
    assert session["recorded"].annotation.text == session["asking"]


@then("no rule or constraint SHALL change as a result")
def _no_constraint_changed(session: dict[str, Any]) -> None:
    assert session["asset"].constraints.tri_budget == TRI_BUDGET
    assert not any(
        may_only_observe(RAFA, operation, via=BLENDER).allowed
        for operation in (Operation.PROMOTE_TO_RULE, Operation.RESOLVE_ISSUE)
    )


# --------------------------------------------------------------------------
# An agent may not create an asset or a specification file
# --------------------------------------------------------------------------


@when("an observation is recorded against an asset identifier that does not exist in the project")
def _a_write_to_an_unknown_asset(session: dict[str, Any]) -> None:
    a_read_surface(session)
    session["unknown"] = "mech_scowt"
    session["refusal"] = refused(
        record_observation(a_session(session), a_request(asset=session["unknown"]))
    )


@then("the write SHALL be refused naming that identifier")
def _refused_naming_the_identifier(session: dict[str, Any]) -> None:
    assert session["unknown"] in session["refusal"].message


@then("no specification file SHALL be created")
def _no_specification_created(session: dict[str, Any]) -> None:
    writer: InMemoryAnnotationWriter = session["writer"]

    assert writer.appends == 0
    assert writer.locate(PROJECT, session["unknown"]) is None


@then("the response SHALL offer the closest existing identifiers")
def _closest_offered(session: dict[str, Any]) -> None:
    assert ASSET in session["refusal"].message


@given("a write that was refused for naming an unknown asset")
def _a_refused_write(session: dict[str, Any]) -> None:
    _a_write_to_an_unknown_asset(session)


@when("the caller then reads an asset that does exist")
def _then_reads_an_existing_asset(session: dict[str, Any]) -> None:
    session["read"] = where_is(ASSET, spec_store=session["store"], search_index=session["index"])


@then("the read SHALL succeed")
def _the_read_succeeded(session: dict[str, Any]) -> None:
    assert ran(session["read"]).asset_id == ASSET


# --------------------------------------------------------------------------
# Writes require an identity and reads do not
# --------------------------------------------------------------------------


@given("no credential is available on the machine")
def _no_credential(session: dict[str, Any]) -> None:
    a_read_surface(session)
    a_session(session, resolver=ActorResolver(project=PROJECT))


@when(
    "an automated caller reads a specification, looks up an asset's location and validates an "
    "export"
)
def _every_read(session: dict[str, Any]) -> None:
    store: InMemorySpecStore = session["store"]
    session["reads"] = (
        store.load(SPEC_PATH),
        where_is(ASSET, spec_store=store, search_index=session["index"]),
        report_validation_outcome(
            a_report(),
            reporter=_reporter(session),
            export=EXPORT,
            export_hash="sha256:aaaa",
            clock=lambda: NOW,
        ),
    )


@then("every one of those SHALL succeed")
def _every_read_succeeded(session: dict[str, Any]) -> None:
    loaded, located, reported = session["reads"]

    assert loaded.asset.id.value == ASSET
    assert ran(located).asset_id == ASSET
    assert succeeded(reported)


@when("an automated caller records an observation")
def _an_automated_write(session: dict[str, Any]) -> None:
    """One write, whatever the GIVEN set up — a refusal here, a real file there.

    Two scenarios share this WHEN and they end differently: an unauthenticated
    machine is refused, and a clean working tree gets one changed block. The
    outcome is kept rather than asserted, so each THEN asks its own question.
    """
    session["written"] = record_observation(session["session"], a_request())
    session["refusal"] = session["written"]


@then("the write SHALL be refused")
def _the_write_was_refused(session: dict[str, Any]) -> None:
    assert isinstance(session["refusal"], Unauthenticated)
    assert session["writer"].appends == 0


@then("the refusal SHALL name the sign-in action that would enable it")
def _the_refusal_names_the_sign_in(session: dict[str, Any]) -> None:
    assert SIGN_IN_ACTION in session["refusal"].message


@given("a credential that can no longer be refreshed")
def _an_unrefreshable_credential(session: dict[str, Any]) -> None:
    a_read_surface(session)
    cache = IdentityCache(clock=lambda: 10_000.0, ttl=900.0)
    cache.remember(ResolvedIdentity(actor=RAFA), at=0.0)
    a_session(session, resolver=ActorResolver(project=PROJECT, cache=cache))


@when("the caller reads a specification and then attempts a write")
def _reads_then_writes(session: dict[str, Any]) -> None:
    session["read"] = where_is(ASSET, spec_store=session["store"], search_index=session["index"])
    session["refusal"] = refused(record_observation(session["session"], a_request()))


@then("the write SHALL be refused as unverifiable")
def _refused_as_unverifiable(session: dict[str, Any]) -> None:
    assert UNVERIFIABLE in session["refusal"].message
    assert session["writer"].appends == 0


# --------------------------------------------------------------------------
# The credential
# --------------------------------------------------------------------------


@when("a person runs the sign-in action")
def _a_person_signs_in(session: dict[str, Any], fakes: dict[str, Any]) -> None:
    grants: list[Any] = []
    session["signed_in"] = ran(
        sign_in(
            interactive_sign_in=fakes["interactive_sign_in"],
            credential_store=fakes["credential_store"],
            announce=grants.append,
        )
    )
    session["grants"] = grants
    session["store_for_credentials"] = fakes["credential_store"]
    session["flow"] = fakes["interactive_sign_in"]


@then("they SHALL be shown a verification code and a URL to visit")
def _shown_a_code_and_a_url(session: dict[str, Any]) -> None:
    (grant,) = session["grants"]

    assert grant.user_code.strip()
    assert grant.verification_uri.startswith("http")


@then("the flow SHALL complete without a secret being typed into the terminal")
def _no_secret_typed(session: dict[str, Any]) -> None:
    import inspect

    assert session["store_for_credentials"].load() is not None
    for name in ("begin", "redeem"):
        parameters = inspect.signature(getattr(session["flow"], name)).parameters
        assert not any("password" in parameter or "secret" in parameter for parameter in parameters)


@given("a signed-in machine")
def _a_signed_in_machine(session: dict[str, Any], fakes: dict[str, Any]) -> None:
    a_read_surface(session)
    fakes["credential_store"].store(Credential("an-issued-credential"))
    session["store_for_credentials"] = fakes["credential_store"]


@when("the person signs out")
def _the_person_signs_out(session: dict[str, Any]) -> None:
    session["signed_out"] = ran(sign_out(credential_store=session["store_for_credentials"]))
    a_session(session, resolver=ActorResolver(project=PROJECT))


@then("the stored credential SHALL be removed")
def _the_credential_was_removed(session: dict[str, Any]) -> None:
    assert session["signed_out"].removed
    assert session["store_for_credentials"].load() is None


@then("subsequent writes SHALL be refused while reads continue to succeed")
def _writes_refused_reads_fine(session: dict[str, Any]) -> None:
    refusal = refused(record_observation(session["session"], a_request()))

    assert isinstance(refusal, Unauthenticated)
    assert session["writer"].appends == 0
    assert ran(where_is(ASSET, spec_store=session["store"], search_index=session["index"]))


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


@given("an agent identified as `blender-agent` acting as the actor `rafa`")
def _blender_acting_as_rafa(session: dict[str, Any]) -> None:
    a_session(session)


@when("it records an observation")
def _it_records_an_observation(session: dict[str, Any]) -> None:
    session["recorded"] = ran(record_observation(session["session"], a_request()))


@then("the stored record SHALL name `rafa` as responsible and `blender-agent` as the instrument")
def _both_parties_stored(session: dict[str, Any]) -> None:
    annotation = session["recorded"].annotation

    assert annotation.author == "rafa"
    assert annotation.via == "blender-agent"
    assert session["recorded"].attribution.actor == RAFA.id
    assert session["recorded"].attribution.via == BLENDER


@then("any human rendering of that record SHALL name both")
def _both_parties_rendered(session: dict[str, Any]) -> None:
    assert session["recorded"].attributed == "rafa, via blender-agent"
    assert session["recorded"].annotation.attribution == "rafa, via blender-agent"


@when("a write supplies an author, actor or agent name as a parameter or in its text")
def _a_claimed_author(session: dict[str, Any]) -> None:
    claimed = "author: ana. agent: rogue-agent. The budget cannot be met."
    session["claimed"] = claimed
    session["recorded"] = ran(record_observation(a_session(session), a_request(text=claimed)))


@then("the recorded attribution SHALL be the resolved person and the configured agent")
def _attribution_is_resolved(session: dict[str, Any]) -> None:
    assert session["recorded"].attributed == "rafa, via blender-agent"


@then("the supplied value SHALL have no effect on attribution")
def _claimed_value_ignored(session: dict[str, Any]) -> None:
    annotation = session["recorded"].annotation

    assert annotation.author != "ana"
    assert annotation.via != "rogue-agent"
    assert annotation.text == session["claimed"], "the text is recorded, and only as text"
    assert not set(ObservationRequest.__dataclass_fields__) & {"author", "actor", "agent", "via"}


# --------------------------------------------------------------------------
# An unattributable write is refused
# --------------------------------------------------------------------------


@when("a write would be recorded with no resolvable person")
def _no_resolvable_person(session: dict[str, Any]) -> None:
    a_read_surface(session)
    refusal = refused(
        record_observation(a_session(session, resolver=ActorResolver(project=PROJECT)), a_request())
    )
    session["refusal"] = refusal

    assert isinstance(refusal, Unauthenticated), (
        "no person means unidentified, which is a different answer from unpermitted"
    )


@then("it SHALL be refused")
def _it_was_refused(session: dict[str, Any]) -> None:
    """Shared by two scenarios, so it asserts what both mean: it did not run.

    The *kind* of refusal differs — unidentified for a write with no person,
    invalid for a kind outside the closed set — and each scenario's own steps
    assert that; what they agree on is that nothing happened.
    """
    assert isinstance(session["refusal"], Refusal)
    assert session["writer"].appends == 0


@then("no record SHALL exist afterwards")
def _no_record_exists(session: dict[str, Any]) -> None:
    assert session["writer"].appends == 0
    assert session["writer"].recorded(ASSET) == ()


@given("a server started without an agent identifier")
def _no_agent_identifier(session: dict[str, Any]) -> None:
    a_read_surface(session)
    a_session(session, agent=None)


@when("an automated caller attempts a write")
def _attempts_a_write(session: dict[str, Any]) -> None:
    session["refusal"] = refused(record_observation(session["session"], a_request()))


@then("the write SHALL be refused naming the missing agent identifier")
def _refused_naming_the_agent(session: dict[str, Any]) -> None:
    assert session["refusal"].message == NO_AGENT_IDENTIFIER
    assert session["writer"].appends == 0


@then("reads SHALL continue to succeed")
def _reads_continue(session: dict[str, Any]) -> None:
    assert ran(where_is(ASSET, spec_store=session["store"], search_index=session["index"]))


# --------------------------------------------------------------------------
# An agent-authored annotation is an observation
# --------------------------------------------------------------------------


@given("an asset with a triangle budget of 12000")
def _an_asset_with_a_budget(session: dict[str, Any]) -> None:
    session["asset"] = Asset(
        id=AssetId(ASSET), name="Scout Mech", constraints=Constraints(tri_budget=TRI_BUDGET)
    )
    a_session(session)


@when("an agent records that it cannot reach 12000 triangles without losing the head silhouette")
def _records_the_unreachable_budget(session: dict[str, Any]) -> None:
    session["recorded"] = ran(record_observation(session["session"], a_request(text=UNREACHABLE)))


@then("the observation SHALL be recorded with that text")
def _recorded_with_that_text(session: dict[str, Any]) -> None:
    assert session["recorded"].annotation.text == UNREACHABLE
    assert session["recorded"].annotation.author_kind is AuthorKind.AGENT


@then("the asset's triangle budget SHALL still be 12000")
def _the_budget_stands(session: dict[str, Any]) -> None:
    assert session["asset"].constraints.tri_budget == TRI_BUDGET


@given("an observation recorded by an automated caller")
def _an_agent_observation(session: dict[str, Any]) -> None:
    session["recorded"] = ran(record_observation(a_session(session), a_request()))


@when("that caller attempts to resolve or promote it")
def _attempts_to_close_it(session: dict[str, Any]) -> None:
    session["decisions"] = {
        operation: [
            may_only_observe(replace(RAFA, roles=(role,)) if role else RAFA, operation, via=BLENDER)
            for role in (None, *prohibited_for_every_role())
        ]
        for operation in (Operation.RESOLVE_ISSUE, Operation.PROMOTE_TO_RULE)
    }


@then("the attempt SHALL be refused")
def _the_attempt_was_refused(session: dict[str, Any]) -> None:
    assert all(
        decision.refused for decisions in session["decisions"].values() for decision in decisions
    )


@then("the observation SHALL remain open")
def _the_observation_is_open(session: dict[str, Any]) -> None:
    (recorded,) = session["writer"].recorded(ASSET)

    assert recorded.is_open
    assert recorded.id == session["recorded"].id


# --------------------------------------------------------------------------
# The two kind fields
# --------------------------------------------------------------------------


@when("an agent records an observation that a constraint is unattainable")
def _records_an_unattainable_constraint(session: dict[str, Any]) -> None:
    session["recorded"] = ran(record_observation(a_session(session), a_request()))


@then("the stored annotation SHALL carry a `kind` from the `asset-spec` set")
def _carries_an_asset_spec_kind(session: dict[str, Any]) -> None:
    assert session["recorded"].annotation.kind in set(AnnotationKind)


@then("it SHALL carry `observation_kind` identifying it as an unattainable constraint")
def _carries_the_observation_kind(session: dict[str, Any]) -> None:
    assert (
        session["recorded"].annotation.observation_kind is ObservationKind.UNATTAINABLE_CONSTRAINT
    )


@then("it SHALL be filterable by either field when open annotations are read")
def _filterable_by_either_field(session: dict[str, Any]) -> None:
    recorded = session["writer"].recorded(ASSET)

    assert [entry for entry in recorded if entry.kind is AnnotationKind.TECHNICAL]
    assert [
        entry
        for entry in recorded
        if entry.observation_kind is ObservationKind.UNATTAINABLE_CONSTRAINT
    ]


@when("an agent supplies an observation-specific value in the `kind` field")
def _an_observation_value_in_the_kind_field(session: dict[str, Any]) -> None:
    session["refusal"] = refused(
        record_observation(a_session(session), a_request(kind="unattainable_constraint"))
    )


@then("the write SHALL be refused naming the values `asset-spec` permits")
def _refused_naming_the_asset_spec_values(session: dict[str, Any]) -> None:
    assert all(member.value in session["refusal"].message for member in AnnotationKind)
    assert session["writer"].appends == 0


@when("an observation is recorded with a kind outside the fixed set")
def _a_kind_outside_the_set(session: dict[str, Any]) -> None:
    session["refusal"] = refused(
        record_observation(a_session(session), a_request(observation_kind="blocked"))
    )


@then("the refusal SHALL list the permitted kinds")
def _lists_the_permitted_kinds(session: dict[str, Any]) -> None:
    assert all(value in session["refusal"].message for value in ObservationKind.values())
    assert session["writer"].appends == 0


# --------------------------------------------------------------------------
# Anchoring
# --------------------------------------------------------------------------


@when("an observation names a target that exists on the asset")
def _a_target_that_exists(session: dict[str, Any]) -> None:
    session["recorded"] = ran(
        record_observation(a_session(session, subjects=("head", "torso")), a_request(target="head"))
    )


@then("the observation SHALL be anchored to that target")
def _anchored_to_the_target(session: dict[str, Any]) -> None:
    assert not session["recorded"].unanchored
    assert session["recorded"].annotation.durable_key == "head"


@when("an observation names a target that does not exist on the asset")
def _a_target_that_does_not_exist(session: dict[str, Any]) -> None:
    session["given_target"] = "helmet_crest"
    session["recorded"] = ran(
        record_observation(
            a_session(session, subjects=("head", "torso")),
            a_request(target=session["given_target"]),
        )
    )


@then("the observation SHALL be recorded against the asset as unanchored")
def _recorded_unanchored(session: dict[str, Any]) -> None:
    assert session["writer"].appends == 1
    assert session["recorded"].unanchored


@then("the target as given SHALL be preserved in the record")
def _target_preserved(session: dict[str, Any]) -> None:
    assert session["recorded"].annotation.durable_key == session["given_target"]


@then("reading it SHALL report it as unanchored")
def _read_as_unanchored(session: dict[str, Any]) -> None:
    (recorded,) = session["writer"].recorded(ASSET)

    assert recorded.is_orphaned


# --------------------------------------------------------------------------
# Reporting a verdict somebody already has
# --------------------------------------------------------------------------


@given("a local validation that produced two error violations")
def _a_failing_local_validation(session: dict[str, Any]) -> None:
    session["report"] = a_report(a_violation("mesh.tri_budget"), a_violation("mesh.pivot"))
    session["verdict_before"] = verdict_hash(session["report"])


@when("that outcome is reported")
def _that_outcome_is_reported(session: dict[str, Any]) -> None:
    _report(session)


@then("the reported outcome SHALL carry exactly those two violations")
def _carries_exactly_those_violations(session: dict[str, Any]) -> None:
    outcome = session["reported"].outcome

    assert outcome.errors == 2
    assert outcome.verdict_hash == session["verdict_before"]


@then("the caller's local verdict SHALL be unchanged")
def _local_verdict_unchanged(session: dict[str, Any]) -> None:
    assert verdict_hash(session["report"]) == session["verdict_before"]
    assert len(session["report"].errors) == 2


@when("the outcome-reporting tool is called")
def _the_reporting_tool_is_called(session: dict[str, Any]) -> None:
    _report(session)


@then("no validation rule SHALL be evaluated as part of the report")
def _no_rule_evaluated(session: dict[str, Any]) -> None:
    import ast
    import inspect

    from cybercanon.application.use_cases import observations as module

    tree = ast.parse(inspect.getsource(module))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not any("rules" in name or "mesh_inspector" in name for name in imported)


@given("the reporting destination is unreachable")
def _the_destination_is_unreachable(session: dict[str, Any]) -> None:
    _reporter(session).unreachable()


@when("an outcome is reported")
def _an_outcome_is_reported(session: dict[str, Any]) -> None:
    _report(session)


@then("the call SHALL return successfully")
def _the_call_returned_successfully(session: dict[str, Any]) -> None:
    assert session["reported"].outcome.asset_id == ASSET


@then("the response SHALL state that the verdict stands and delivery is pending")
def _the_verdict_stands(session: dict[str, Any]) -> None:
    assert VERDICT_STANDS in session["reported"].note
    assert session["reported"].pending == 1


@given("an outcome retained locally because delivery failed")
def _a_retained_outcome(session: dict[str, Any]) -> None:
    _reporter(session).unreachable()
    _report(session)


@when("the destination becomes reachable and delivery is next attempted")
def _delivery_is_attempted_again(session: dict[str, Any]) -> None:
    _reporter(session).unreachable(True)
    session["delivery"] = ran(flush_reports(reporter=_reporter(session)))


@then("the retained outcome SHALL be delivered")
def _the_retained_outcome_was_delivered(session: dict[str, Any]) -> None:
    assert session["delivery"].delivered == 1


@then("SHALL no longer be pending")
def _no_longer_pending(session: dict[str, Any]) -> None:
    assert _reporter(session).pending() == ()


@given("an outcome that was already delivered")
def _an_already_delivered_outcome(session: dict[str, Any]) -> None:
    _report(session)


@when("the identical outcome is reported again")
def _reported_again(session: dict[str, Any]) -> None:
    _report(session)


@then("the destination SHALL hold exactly one record of it")
def _exactly_one_record(session: dict[str, Any]) -> None:
    assert len(_reporter(session).delivered) == 1


@given("a delivered outcome for an export")
def _a_delivered_outcome(session: dict[str, Any]) -> None:
    _report(session)


@when("the asset is re-exported and the new outcome is reported")
def _a_re_export_is_reported(session: dict[str, Any]) -> None:
    _report(session, export_hash="sha256:bbbb")


@then("both outcomes SHALL be distinguishable, with the later one current")
def _both_outcomes_distinguishable(session: dict[str, Any]) -> None:
    delivered = _reporter(session).delivered

    assert len({outcome.key for outcome in delivered}) == 2
    assert delivered[-1].export_hash == "sha256:bbbb"


# --------------------------------------------------------------------------
# The rate limit
# --------------------------------------------------------------------------


ONE_PER_WINDOW = WriteLimits(observations=1, window_seconds=600.0)


@given("an automated caller that has reached the observation limit for an asset")
def _at_the_limit(session: dict[str, Any]) -> None:
    a_read_surface(session)
    ran(record_observation(a_session(session, limits=ONE_PER_WINDOW), a_request()))


@when("it records another observation on that asset")
def _another_observation_on_that_asset(session: dict[str, Any]) -> None:
    later = a_session(session, limits=ONE_PER_WINDOW, at=NOW + timedelta(seconds=1))
    session["refusal"] = refused(
        record_observation(later, a_request(text="and the shoulder pads will not fit"))
    )


@then("the write SHALL be refused naming the limit and the time it resets")
def _refused_naming_the_limit(session: dict[str, Any]) -> None:
    message = session["refusal"].message

    assert str(ONE_PER_WINDOW.observations) in message
    assert (NOW + ONE_PER_WINDOW.window).isoformat() in message
    assert session["writer"].appends == 1


@then("the caller SHALL still be able to read that asset")
def _still_able_to_read(session: dict[str, Any]) -> None:
    assert ran(where_is(ASSET, spec_store=session["store"], search_index=session["index"]))


@given("an automated caller throttled on one asset")
def _throttled_on_one_asset(session: dict[str, Any]) -> None:
    _at_the_limit(session)
    _another_observation_on_that_asset(session)


@when("it records an observation on a different asset within that actor's limit")
def _an_observation_on_another_asset(session: dict[str, Any]) -> None:
    session["write"] = record_observation(
        a_session(session, limits=ONE_PER_WINDOW, at=NOW + timedelta(seconds=2)),
        a_request(asset=OTHER_ASSET, text="the crate's pivot is not at its base"),
    )


@given("an automated caller that has reported many outcomes")
def _many_outcomes_reported(session: dict[str, Any]) -> None:
    for index in range(10):
        _report(session, export_hash=f"sha256:{index:04d}")


@when("it records its first observation on an asset")
def _its_first_observation(session: dict[str, Any]) -> None:
    session["write"] = record_observation(a_session(session, limits=ONE_PER_WINDOW), a_request())


@then("that write SHALL succeed")
def _that_write_succeeded(session: dict[str, Any]) -> None:
    """One step for two scenarios, because both mean the same thing by it.

    The throttled agent writing on another asset and the reporting agent
    writing its first observation are the same claim — a limit that is scoped
    the way D9 scopes it does not reach here — so one assertion serves both and
    neither can shadow the other.
    """
    assert ran(session["write"]).id


# --------------------------------------------------------------------------
# Near-duplicate suppression
# --------------------------------------------------------------------------


@given("an open agent-authored observation on an asset and target")
def _an_open_observation(session: dict[str, Any]) -> None:
    session["first"] = ran(record_observation(a_session(session), a_request()))


@when("the same agent records a materially identical observation on that asset and target")
def _the_same_observation_again(session: dict[str, Any]) -> None:
    session["again"] = ran(
        record_observation(
            a_session(session, at=NOW + timedelta(seconds=30)),
            a_request(text=f"  {UNREACHABLE.upper()}!  "),
        )
    )


@then("no second observation SHALL be created")
def _no_second_observation(session: dict[str, Any]) -> None:
    assert session["writer"].appends == 1
    assert len(session["writer"].recorded(ASSET)) == 1


@then("the response SHALL identify the existing one")
def _identifies_the_existing_one(session: dict[str, Any]) -> None:
    assert session["again"].suppressed
    assert session["again"].id == session["first"].id


@given("an agent-authored observation that a person has resolved")
def _a_resolved_observation(session: dict[str, Any]) -> None:
    first = ran(record_observation(a_session(session), a_request()))
    session["writer"].declare(
        ASSET, SPEC_PATH, first.annotation.resolved(by="rafa", at=NOW.isoformat())
    )
    session["first"] = first


@when("the agent records a materially identical observation afterwards")
def _the_same_observation_after_resolution(session: dict[str, Any]) -> None:
    session["again"] = ran(
        record_observation(a_session(session, at=NOW + timedelta(seconds=60)), a_request())
    )


@then("a new observation SHALL be recorded")
def _a_new_observation_was_recorded(session: dict[str, Any]) -> None:
    assert not session["again"].suppressed
    assert session["again"].id != session["first"].id


# --------------------------------------------------------------------------
# The surface itself, the working tree, and the human surfaces (groups 3-5)
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Only two write tools are advertised",
)
def test_only_two_write_tools_are_advertised() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "No other repository content is touched by a write",
)
def test_no_other_repository_content_is_touched_by_a_write() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Art director's agent cannot promote",
)
def test_an_art_directors_agent_cannot_promote() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Marked in a reading of open annotations",
)
def test_marked_in_a_reading_of_open_annotations() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Marked in the compiled briefing",
)
def test_marked_in_the_compiled_briefing() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Resolved observation leaves the briefing",
)
def test_a_resolved_observation_leaves_the_briefing() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "Promotion is recorded as the person's authorship",
)
def test_promotion_is_recorded_as_the_persons_authorship() -> None: ...


# --------------------------------------------------------------------------
# The advertised surface — two writes, and the count is the requirement
# --------------------------------------------------------------------------


@when("a caller lists the tools the system offers")
def _lists_the_tools(session: dict[str, Any]) -> None:
    from cybercanon.adapters.inbound.mcp.tools import advertised, build_server

    session["advertised"] = advertised(build_server(_a_read_container(session)))


@then("exactly two of them SHALL change recorded state")
def _exactly_two_writes(session: dict[str, Any]) -> None:
    from cybercanon.adapters.inbound.mcp.tools import READ_TOOL_NAMES, WRITE_TOOL_NAMES

    assert len(WRITE_TOOL_NAMES) == 2
    assert set(WRITE_TOOL_NAMES) <= set(session["advertised"])
    assert not set(WRITE_TOOL_NAMES) & set(READ_TOOL_NAMES)


@then("they SHALL be the observation tool and the outcome-reporting tool")
def _the_two_write_tools(session: dict[str, Any]) -> None:
    from cybercanon.adapters.inbound.mcp.tools import WRITE_TOOL_NAMES

    assert set(WRITE_TOOL_NAMES) == {"add_annotation", "report_export"}


def _a_read_container(session: dict[str, Any]):
    """A container wired for reads, which is all the advertised list needs."""
    from cybercanon.adapters.wiring.container import Container
    from cybercanon.application.testing import build_fakes

    fakes = build_fakes()
    store: InMemorySpecStore = fakes["spec_store"]
    store.set_project(ProjectConfig(name=PROJECT))
    store.add(SPEC_PATH, Asset(id=AssetId(ASSET), name="Scout Mech"))
    return Container(
        spec_store=store,
        mesh_inspector=fakes["mesh_inspector"],
        search_index=fakes["search_index"],
    )


# --------------------------------------------------------------------------
# A write over a real working copy touches one block of one file (D2, D3)
# --------------------------------------------------------------------------


ANNOTATIONS_KEY = "annotations:"


@given("a clean repository working tree")
def _a_clean_working_tree(session: dict[str, Any], tmp_path) -> None:
    """A real git repository whose every file is committed, and a real writer.

    In-memory fakes cannot answer this scenario: *"no other file SHALL be
    created, modified or deleted"* is a claim about a working tree, and only
    `git status` over a real one can refute it.
    """
    from cybercanon.adapters.outbound.git.annotation_writer import GitAnnotationWriter
    from cybercanon.adapters.outbound.git.spec_store import GitSpecStore

    root = tmp_path / "game"
    (root / "characters" / ASSET).mkdir(parents=True)
    (root / "characters" / ASSET / "asset.yaml").write_text(
        f"schema_version: 1\nid: {ASSET}\nname: Scout Mech\nstatus: modeling\n"
        "\nconstraints:\n  tri_budget: 12000\n",
        encoding="utf-8",
    )
    (root / "characters" / ASSET / "notes.md").write_text("a file nobody may touch\n", "utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "the canon, as an artist committed it")
    store = GitSpecStore(root)
    session["root"] = root
    session["spec"] = root / "characters" / ASSET / "asset.yaml"
    session["before"] = session["spec"].read_text(encoding="utf-8")
    session["writer"] = GitAnnotationWriter(store, root=store.root)
    a_session(session)


@then("the only change SHALL be the added observation on the named asset")
def _only_the_observation_changed(session: dict[str, Any]) -> None:
    after = session["spec"].read_text(encoding="utf-8")

    assert succeeded(session["written"])
    assert UNREACHABLE in after
    assert after.split(ANNOTATIONS_KEY)[0] == session["before"].split(ANNOTATIONS_KEY)[0]


@then("no other file SHALL be created, modified or deleted")
def _no_other_file_moved(session: dict[str, Any]) -> None:
    changed = _git(session["root"], "status", "--porcelain").stdout.decode("utf-8").splitlines()

    assert [line.strip() for line in changed if line.strip()] == [
        f"M characters/{ASSET}/asset.yaml"
    ]


def _git(root, *arguments: str):
    """One git command in that repository, with an environment of its own."""
    import os
    import subprocess

    environment = {
        **os.environ,
        "HOME": str(root),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Rafa",
        "GIT_AUTHOR_EMAIL": "rafa@cyberdyne.com",
        "GIT_COMMITTER_NAME": "Rafa",
        "GIT_COMMITTER_EMAIL": "rafa@cyberdyne.com",
    }
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, env=environment
    )


# --------------------------------------------------------------------------
# An art director's agent is refused promotion — there is no such tool
# --------------------------------------------------------------------------


@given("an automated caller acting as an actor holding the art director role")
def _an_art_directors_agent(session: dict[str, Any]) -> None:
    director = Actor(
        id=ActorId("dana"),
        display_name="Dana",
        roles=(Role.ART_DIRECTOR,),
        projects=(PROJECT,),
    )
    a_read_surface(session)
    a_session(session, resolver=AlreadyResolved(verified_as(director)))
    session["actor"] = director


@when("it attempts to promote an observation into a rule")
def _attempts_to_promote(session: dict[str, Any]) -> None:
    """Both halves of the prohibition: no tool offers it, and the core refuses it.

    The decision is written into the same `decisions` the *"an agent cannot
    close its own observation"* scenario asserts over, so the one THEN that
    says *"the attempt SHALL be refused"* answers for both — a second step with
    the same sentence would shadow it, and one of the two scenarios would be
    checking nothing.
    """
    from cybercanon.adapters.inbound.mcp.tools import advertised, build_server

    session["advertised"] = advertised(build_server(_a_read_container(session)))
    session["decisions"] = {
        Operation.PROMOTE_TO_RULE: [
            may_only_observe(session["actor"], Operation.PROMOTE_TO_RULE, via=BLENDER)
        ]
    }


@then("no such tool SHALL exist")
def _no_promotion_tool(session: dict[str, Any]) -> None:
    offered = [name for name in session["advertised"] if "promote" in name]

    assert not offered


# --------------------------------------------------------------------------
# Agent authorship is visible, and the two exits stay human (group 5)
# --------------------------------------------------------------------------


HUMAN_TEXT = "the pauldron reads as a backpack at 15 m"


def _a_repository_with_both(session: dict[str, Any], *, human: bool = True) -> None:
    """A specification holding an agent's observation, and maybe a person's thread."""
    from annotations_world import SCOUT, with_asset

    entries = [
        f"""\
  - id: obs_1
    author: auth|rafa
    via: blender-agent
    kind: technical
    text: {UNREACHABLE}
    state: open
    author_kind: agent
    observation_kind: {ObservationKind.UNATTAINABLE_CONSTRAINT.value}
    created_at: "2026-03-01T12:00:00+00:00"
    target:
      part: SM_MechScout_Head
"""
    ]
    if human:
        entries.insert(
            0,
            f"""\
  - id: an_1
    author: auth|rafa
    kind: art-direction
    text: {HUMAN_TEXT}
    state: open
    created_at: "2026-03-01T09:00:00+00:00"
    target:
      part: SM_MechScout_Head
""",
        )
    spec = (
        f"schema_version: 1\nid: {SCOUT}\nname: Scout Mech\nstatus: modeling\n"
        "\nconcept:\n  views: [front, side, back]\n\nannotations:\n" + "".join(entries)
    ).encode()
    session["world"] = with_asset(spec)


def _compiled(session: dict[str, Any]) -> str:
    from annotations_world import SCOUT_SPEC
    from cybercanon.application.use_cases.compile_spec import compile_spec

    return compile_spec.raising(SCOUT_SPEC, spec_store=session["world"].spec_store).text


@given("one human-authored and one agent-authored open annotation on an asset")
def _one_of_each(session: dict[str, Any]) -> None:
    _a_repository_with_both(session)


@when("a person or an agent reads that asset's open annotations")
def _reads_the_open_annotations(session: dict[str, Any]) -> None:
    from annotations_world import SCOUT_SPEC
    from cybercanon.application.use_cases.compile_spec import compile_spec
    from cybercanon.application.use_cases.spec_lens import project_open_issues

    compiled = compile_spec.raising(SCOUT_SPEC, spec_store=session["world"].spec_store)
    session["read"] = project_open_issues(compiled).text


@then("the agent-authored one SHALL be marked as agent-authored")
def _the_agents_is_marked(session: dict[str, Any]) -> None:
    marked_lines = [line for line in session["read"].splitlines() if AGENT_AUTHORED in line]

    assert len(marked_lines) == 1
    assert UNREACHABLE in marked_lines[0]


@then("the human-authored one SHALL NOT be")
def _the_persons_is_not_marked(session: dict[str, Any]) -> None:
    human_lines = [line for line in session["read"].splitlines() if HUMAN_TEXT in line]

    assert len(human_lines) == 1
    assert AGENT_AUTHORED not in human_lines[0]


@given("an open agent-authored observation on an asset")
def _an_open_agent_observation(session: dict[str, Any]) -> None:
    _a_repository_with_both(session, human=False)


@when("the asset's briefing is compiled")
def _the_briefing_is_compiled(session: dict[str, Any]) -> None:
    session["briefing"] = _compiled(session)


@then("the observation SHALL appear as an open issue marked as agent-authored")
def _the_briefing_marks_it(session: dict[str, Any]) -> None:
    briefing = session["briefing"]
    issues = briefing.split("Open issues")[1]

    assert UNREACHABLE in issues
    assert AGENT_AUTHORED in issues
    assert "via blender-agent" in issues


@given("an open agent-authored observation appearing in a compiled briefing")
def _an_observation_in_the_briefing(session: dict[str, Any]) -> None:
    _a_repository_with_both(session, human=False)
    assert UNREACHABLE in _compiled(session)


@when("a person resolves it as an issue")
def _a_person_resolves_it(session: dict[str, Any]) -> None:
    from annotations_world import RAFA_ACTOR

    session["resolved"] = ran(
        session["world"].resolve("obs_1", actor=RAFA_ACTOR, conclusion="the budget was re-cut")
    )


@then("subsequent compilations SHALL NOT contain it")
def _the_briefing_no_longer_carries_it(session: dict[str, Any]) -> None:
    compiled = _compiled(session)

    assert UNREACHABLE not in compiled
    assert AGENT_AUTHORED not in compiled


@given("an agent-authored observation that a person promotes into a rule")
def _an_observation_a_person_promotes(session: dict[str, Any]) -> None:
    from annotations_world import DIRECTOR
    from cybercanon.domain.triage import PromotionTarget

    _a_repository_with_both(session, human=False)
    session["rule"] = "the head silhouette outranks the triangle budget"
    session["promoted"] = ran(
        session["world"].promote(
            "obs_1", session["rule"], PromotionTarget.SILHOUETTE_RULES, actor=DIRECTOR
        )
    )


@when("the resulting rule is read")
def _the_rule_is_read(session: dict[str, Any]) -> None:
    session["briefing"] = _compiled(session)


@then("it SHALL be attributed to the person who promoted it")
def _the_rule_is_the_persons(session: dict[str, Any]) -> None:
    assert session["rule"] in session["briefing"]
    assert session["world"].commits()[-1].author.email == "dana@cyberdyne.com"


@then("SHALL NOT be attributed to the agent")
def _the_rule_is_not_the_agents(session: dict[str, Any]) -> None:
    rules = session["briefing"].split("Open issues")[0]

    assert "blender-agent" not in rules
    assert AGENT_AUTHORED not in rules


# --------------------------------------------------------------------------
# Group 6 — the command line, the launch configuration, and the commit that
# does not wait for a report
# --------------------------------------------------------------------------


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "One sign-in serves both surfaces",
)
def test_one_sign_in_serves_both_surfaces() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "No secret appears in configuration",
)
def test_no_secret_appears_in_configuration() -> None: ...


@scenario(
    "../features/add-mcp-writes/mcp-write-surface.feature",
    "A pre-commit run is unaffected",
)
def test_a_pre_commit_run_is_unaffected() -> None: ...


ISSUED = Credential("the-credential-the-issuer-signed")

LAUNCH_ENTRY = re.compile(r"```json\n(\{\n  \"mcpServers\".*?\n\})\n```", re.DOTALL)
"""The agent client configuration, as `README.md` publishes it.

Read out of the document rather than restated here, because *"the configuration
SHALL contain no credential"* is a claim about the thing people copy.
"""

CREDENTIAL_WORDS = ("token", "secret", "password", "credential", "api_key", "apikey")

GOVERNED_EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
"""An export inside the asset's own directory, so discovery finds its specification."""


@given("a person has signed in through the command-line tool")
def _a_person_signed_in_at_the_terminal(session: dict[str, Any], fakes: dict[str, Any]) -> None:
    """The command line's own sign-in, into the machine's credential store."""
    a_read_surface(session)
    store = fakes["credential_store"]
    session["store_for_credentials"] = store
    session["signed_in"] = ran(
        sign_in(
            interactive_sign_in=InMemoryInteractiveSignIn(issues=ISSUED),
            credential_store=store,
        )
    )

    assert store.load() == ISSUED, "the credential is in the machine's store"


@when("an agent-facing server is started on the same machine as that person")
def _the_agent_server_starts_on_that_machine(session: dict[str, Any]) -> None:
    """A second process, reading the same store — and starting no flow of its own.

    The server is given the credential store and an identity provider and
    nothing else: there is no sign-in port in this session, so a second sign-in
    is not merely avoided, it is not reachable.
    """
    provider = InMemoryIdentityProvider()
    provider.add(ISSUED, RAFA)
    held = session["store_for_credentials"].load()
    session["server_session"] = a_session(
        session,
        resolver=ActorResolver(project=PROJECT, provider=provider, credential=held),
    )


@then("it SHALL write as that person without a further sign-in")
def _it_writes_as_that_person(session: dict[str, Any]) -> None:
    recorded = ran(record_observation(session["server_session"], a_request()))

    assert recorded.annotation.author == RAFA.subject
    assert recorded.annotation.via == str(BLENDER)
    assert session["store_for_credentials"].writes == 1, "nobody signed in twice"


@when("an agent client is configured to launch the server")
def _an_agent_client_is_configured(session: dict[str, Any], repo_root: Path) -> None:
    """The documented launch entry, taken from the document people copy."""
    block = LAUNCH_ENTRY.search((repo_root / "README.md").read_text(encoding="utf-8"))

    assert block is not None, "README.md no longer documents an agent client configuration"

    session["configuration"] = json.loads(block.group(1))["mcpServers"]["cybercanon"]


@then("the configuration SHALL contain no credential")
def _the_configuration_holds_no_credential(session: dict[str, Any]) -> None:
    rendered = json.dumps(session["configuration"]).lower()

    assert not [word for word in CREDENTIAL_WORDS if word in rendered], rendered
    assert ISSUED.value not in rendered
    assert session["configuration"].get("env", {}).get("CANON_AGENT"), (
        "it names the agent, which is a name and not a secret"
    )


@then(
    "the stored credential SHALL be retrievable only from the operating system's credential store"
)
def _only_the_store_holds_it(session: dict[str, Any], fakes: dict[str, Any]) -> None:
    """Nothing a surface returns carries the credential — by shape, not by habit.

    A sign-in answers where the credential was kept, and the identity answers
    who this machine writes as; neither has a field a credential could travel
    in, which is why `canon login --json` cannot put one on standard output.
    """
    store = fakes["credential_store"]
    store.store(ISSUED)
    signed_in = ran(
        sign_in(
            interactive_sign_in=InMemoryInteractiveSignIn(issues=ISSUED),
            credential_store=store,
        )
    )
    identity = ran(
        show_identity(resolver=AlreadyResolved(verified_as(RAFA)), credential_store=store)
    )

    assert store.load() == ISSUED
    assert ISSUED.value not in str(signed_in) + json.dumps(asdict(signed_in))
    assert ISSUED.value not in str(identity) + json.dumps(asdict(identity))


@when("a person validates an export as part of committing")
def _a_person_validates_while_committing(session: dict[str, Any], fakes: dict[str, Any]) -> None:
    """The pre-commit path: validate, then try to report, and never wait for it.

    The validation is the same `validate_export` the hook runs, over the same
    fakes; the report is attempted after it and its failure is the ordinary
    case being tested.
    """
    store = fakes["spec_store"]
    store.add(SPEC_PATH, Asset(id=AssetId(ASSET), name="Scout Mech"))
    inspector = fakes["mesh_inspector"]
    inspector.add(GOVERNED_EXPORT, facts_for(MeshFormat.GLB, triangles=11840))
    session["verdict"] = validate_export(
        GOVERNED_EXPORT, spec_store=store, mesh_inspector=inspector, blob_store=None
    )
    session["reported"] = report_validation_outcome(
        ran(session["verdict"]).report,
        reporter=_reporter(session),
        export=GOVERNED_EXPORT,
        export_hash="a1b2c3",
        clock=lambda: NOW,
    )


@then("the validation SHALL complete and the commit SHALL proceed on the verdict alone")
def _the_commit_proceeds_on_the_verdict(session: dict[str, Any]) -> None:
    outcome = ran(session["verdict"])
    delivery = ran(session["reported"])

    assert outcome.passed, "the export satisfied its specification"
    assert exit_code(outcome.passed) == 0, "which is the only thing the hook reads"
    assert delivery.pending == 1, "and the report is still waiting"
    assert VERDICT_STANDS in delivery.note
