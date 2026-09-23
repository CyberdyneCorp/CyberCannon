"""Tasks 2.3 to 2.9 — the write use cases, over fakes and a clock a test chose.

The whole of what an automated caller may do, asserted at the layer that
decides it. Five claims are worth stating as claims, because they are the ones
the requirement is actually about and the ones a later change is most likely to
break by accident:

* **a refusal records nothing.** Every refusal path is asserted against the
  writer's own contents afterwards, not against a return value — a use case that
  refused *after* appending would pass a message assertion and fail this one;
* **ordering is a requirement, not an implementation detail.** An unknown asset
  is refused before the rate limit is consulted, so a typo cannot throttle an
  artist's agent for the next hour;
* **reads never acquire an identity requirement.** The no-credential and
  expired-credential tests run real read use cases beside the refused write, so
  "writes require an identity and reads do not" is checked in one breath;
* **a claimed author has no effect**, whether it arrives as a parameter or in
  the text of the observation itself;
* **reporting evaluates nothing.** Asserted structurally, over the module's own
  imports, because a test that merely counted calls would pass the day somebody
  imported the rule registry for something else.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from cybercanon.application.ports.annotation_writer import AnnotationWriter
from cybercanon.application.ports.identity_provider import Credential, ResolvedIdentity
from cybercanon.application.ports.outcome_reporter import VERDICT_STANDS
from cybercanon.application.ports.search_index import IndexedAsset
from cybercanon.application.ports.spec_store import ProjectConfig
from cybercanon.application.results import Forbidden, NotFound, Unauthenticated, succeeded
from cybercanon.application.testing.annotation_writer import InMemoryAnnotationWriter
from cybercanon.application.testing.credential_store import InMemoryCredentialStore
from cybercanon.application.testing.interactive_sign_in import InMemoryInteractiveSignIn
from cybercanon.application.testing.outcome_reporter import InMemoryOutcomeReporter
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.search_index import InMemorySearchIndex
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases import observations as observations_module
from cybercanon.application.use_cases.lookup_assets import list_assets, where_is
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
from cybercanon.domain.annotations import AnnotationKind, AuthorKind, ObservationKind
from cybercanon.domain.asset import Asset, AssetId
from cybercanon.domain.identity import Actor, ActorId, AgentId, Role
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.observations import WriteLimits
from cybercanon.domain.report import Report
from cybercanon.domain.validation_outcome import verdict_hash
from cybercanon.domain.violations import Severity, Violation

pytestmark = pytest.mark.unit

PROJECT = "ronin"
ASSET = "mech_scout"
SPEC_PATH = "characters/mech_scout/asset.yaml"
BLENDER = AgentId("blender-agent")
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
UNREACHABLE_BUDGET = "12000 triangles is unreachable without losing the head silhouette"

RAFA = Actor(
    id=ActorId("rafa"),
    display_name="Rafa",
    roles=(Role.ARTIST,),
    projects=(PROJECT,),
)


def a_request(**overrides: str) -> ObservationRequest:
    fields = {
        "asset": ASSET,
        "target": "head",
        "text": UNREACHABLE_BUDGET,
        "kind": AnnotationKind.TECHNICAL.value,
        "observation_kind": ObservationKind.UNATTAINABLE_CONSTRAINT.value,
    }
    return ObservationRequest(**(fields | overrides))


def a_writer(*assets: str) -> InMemoryAnnotationWriter:
    writer = InMemoryAnnotationWriter()
    for asset in assets or (ASSET,):
        writer.declare(asset, f"characters/{asset}/asset.yaml")
    return writer


def a_session(
    writer: InMemoryAnnotationWriter | None = None,
    *,
    actor: Actor = RAFA,
    agent: AgentId | None = BLENDER,
    at: datetime = NOW,
    limits: WriteLimits | None = None,
    subjects: tuple[str, ...] | None = None,
    search_index: InMemorySearchIndex | None = None,
) -> WriteSession:
    return WriteSession(
        project=PROJECT,
        resolver=AlreadyResolved(verified_as(actor)),
        writer=writer or a_writer(),
        agent=agent,
        search_index=search_index,
        subjects=None if subjects is None else (lambda _asset: subjects),
        clock=lambda: at,
        limits=limits or WriteLimits(),
    )


def a_report(*violations: Violation) -> Report:
    return Report(
        asset_id=ASSET,
        export_format=MeshFormat.GLB,
        export="exports/mech_scout.glb",
        violations=violations,
        passed_rules=("mesh.up_axis",),
    )


def a_violation(rule_id: str = "mesh.tri_budget") -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=Severity.ERROR,
        subject=ASSET,
        message=f"{ASSET} exceeds its triangle budget",
    )


# --------------------------------------------------------------------------
# 2.3 — the happy path, and the ordering of the refusals
# --------------------------------------------------------------------------


def test_an_observation_is_recorded_against_an_existing_asset() -> None:
    writer = a_writer()

    recorded = ran(record_observation(a_session(writer), a_request()))

    assert recorded.annotation.text == UNREACHABLE_BUDGET
    assert recorded.path == SPEC_PATH
    assert writer.recorded(ASSET) == (recorded.annotation,)


def test_a_recorded_observation_is_marked_agent_authored_and_carries_both_kinds() -> None:
    recorded = ran(record_observation(a_session(), a_request()))

    assert recorded.annotation.author_kind is AuthorKind.AGENT
    assert recorded.annotation.kind is AnnotationKind.TECHNICAL
    assert recorded.annotation.observation_kind is ObservationKind.UNATTAINABLE_CONSTRAINT


def test_a_recorded_observation_names_the_person_and_the_agent() -> None:
    recorded = ran(record_observation(a_session(), a_request()))

    assert recorded.attributed == "rafa, via blender-agent"
    assert recorded.attribution.actor == RAFA.id
    assert recorded.attribution.via == BLENDER


def test_a_local_write_says_it_is_uncommitted() -> None:
    """D2: the response names the file and says the change is not committed."""
    recorded = ran(record_observation(a_session(), a_request()))

    assert not recorded.committed
    assert "uncommitted" in recorded.note or "not committed" in recorded.note


def test_an_observation_is_created_open_and_takes_no_exit() -> None:
    recorded = ran(record_observation(a_session(), a_request()))

    assert recorded.annotation.is_open
    assert not recorded.annotation.closed_by


def test_an_unknown_asset_is_refused_naming_it_and_offering_the_closest() -> None:
    index = InMemorySearchIndex()
    index.upsert(
        IndexedAsset(asset_id=ASSET, name="Scout Mech", project=PROJECT, spec_path=SPEC_PATH)
    )
    writer = a_writer()

    outcome = refused(
        record_observation(a_session(writer, search_index=index), a_request(asset="mech_scowt"))
    )

    assert isinstance(outcome, NotFound)
    assert "mech_scowt" in outcome.message
    assert ASSET in outcome.message
    assert writer.appends == 0


def test_an_unknown_asset_is_refused_before_the_rate_limit_is_consumed() -> None:
    """A typo must not throttle an agent for the next hour."""
    writer = a_writer()
    session = a_session(writer, limits=WriteLimits(observations=1, window_seconds=600.0))

    refused(record_observation(session, a_request(asset="mech_scowt")))
    recorded = ran(record_observation(session, a_request()))

    assert recorded.annotation.id
    assert writer.appends == 1


def test_a_refusal_leaves_the_session_usable() -> None:
    """*"When the caller then reads an asset that does exist, the read SHALL succeed."*"""
    writer = a_writer()
    session = a_session(writer)

    refused(record_observation(session, a_request(asset="mech_scowt")))

    assert writer.locate(PROJECT, ASSET) == SPEC_PATH


def test_a_throttled_write_names_the_limit_and_its_reset_and_records_nothing() -> None:
    writer = a_writer()
    session = a_session(writer, limits=WriteLimits(observations=1, window_seconds=600.0))
    ran(record_observation(session, a_request()))

    outcome = refused(
        record_observation(
            replace(session, clock=lambda: NOW + timedelta(seconds=1)),
            a_request(text="and the shoulder pads will not fit either"),
        )
    )

    assert "limit" in outcome.message or "1" in outcome.message
    assert writer.appends == 1


def test_a_write_after_the_window_succeeds_again() -> None:
    writer = a_writer()
    limits = WriteLimits(observations=1, window_seconds=600.0)
    ran(record_observation(a_session(writer, limits=limits), a_request()))

    later = a_session(writer, limits=limits, at=NOW + timedelta(seconds=601))
    ran(record_observation(later, a_request(text="a second, later finding")))

    assert writer.appends == 2


def test_throttling_on_one_asset_does_not_stop_work_on_another() -> None:
    writer = a_writer(ASSET, "crate")
    limits = WriteLimits(observations=1, window_seconds=600.0)
    session = a_session(writer, limits=limits)
    ran(record_observation(session, a_request()))

    ran(record_observation(session, a_request(asset="crate")))

    assert writer.appends == 2


def test_an_identical_repeat_is_suppressed_and_identifies_the_existing_thread() -> None:
    writer = a_writer()
    session = a_session(writer)
    first = ran(record_observation(session, a_request()))

    again = ran(record_observation(session, a_request(text=UNREACHABLE_BUDGET.upper())))

    assert again.suppressed
    assert again.id == first.id
    assert writer.appends == 1
    assert first.id in again.note


def test_a_repeat_after_a_person_resolved_it_is_recorded_again() -> None:
    writer = a_writer()
    session = a_session(writer)
    first = ran(record_observation(session, a_request()))
    writer.declare(ASSET, SPEC_PATH, first.annotation.resolved(by="rafa", at=NOW.isoformat()))

    later = a_session(writer, at=NOW + timedelta(seconds=60))
    again = ran(record_observation(later, a_request()))

    assert not again.suppressed
    assert again.id != first.id


@pytest.mark.parametrize(
    ("field", "value"),
    [("kind", "unattainable_constraint"), ("kind", "engineering"), ("observation_kind", "blocked")],
)
def test_an_unrecognised_kind_is_refused_listing_the_permitted_values(
    field: str, value: str
) -> None:
    writer = a_writer()

    outcome = refused(record_observation(a_session(writer), a_request(**{field: value})))

    assert "permitted" in outcome.message
    assert writer.appends == 0


def test_an_unresolvable_target_is_recorded_unanchored_with_the_target_preserved() -> None:
    session = a_session(subjects=("head", "torso"))

    recorded = ran(record_observation(session, a_request(target="helmet_crest")))

    assert recorded.unanchored
    assert recorded.annotation.durable_key == "helmet_crest"


def test_a_resolvable_target_anchors_to_it() -> None:
    session = a_session(subjects=("head", "torso"))

    recorded = ran(record_observation(session, a_request(target="head")))

    assert not recorded.unanchored
    assert recorded.annotation.durable_key == "head"


def test_a_conflicted_specification_refuses_and_records_nothing() -> None:
    writer = a_writer()
    writer.refuse_with("the specification file is in conflict")

    outcome = refused(record_observation(a_session(writer), a_request()))

    assert "conflict" in outcome.message
    assert writer.appends == 0


# --------------------------------------------------------------------------
# 2.4, 2.5 — writes require an identity; reads do not
# --------------------------------------------------------------------------


def a_read_surface() -> tuple[InMemorySpecStore, InMemorySearchIndex]:
    store = InMemorySpecStore()
    store.add(SPEC_PATH, Asset(id=AssetId(ASSET), name="Scout Mech"))
    store.set_project(ProjectConfig())
    index = InMemorySearchIndex()
    index.upsert(
        IndexedAsset(asset_id=ASSET, name="Scout Mech", project=PROJECT, spec_path=SPEC_PATH)
    )
    return store, index


def test_with_no_credential_every_read_succeeds_and_the_write_is_refused() -> None:
    store, index = a_read_surface()
    writer = a_writer()
    session = WriteSession(
        project=PROJECT,
        resolver=ActorResolver(project=PROJECT),
        writer=writer,
        agent=BLENDER,
        clock=lambda: NOW,
    )

    assert ran(list_assets(spec_store=store, search_index=index)).asset_ids == (ASSET,)
    assert ran(where_is(ASSET, spec_store=store, search_index=index)).asset_id == ASSET

    outcome = refused(record_observation(session, a_request()))
    assert isinstance(outcome, Unauthenticated)
    assert SIGN_IN_ACTION in outcome.message
    assert writer.appends == 0


def test_an_unrefreshable_credential_refuses_the_write_as_unverifiable() -> None:
    """The read keeps working; the write is refused for a different reason (2.5)."""
    store, index = a_read_surface()
    cache = IdentityCache(clock=lambda: 10_000.0, ttl=900.0)
    cache.remember(ResolvedIdentity(actor=RAFA), at=0.0)
    writer = a_writer()
    session = WriteSession(
        project=PROJECT,
        resolver=ActorResolver(project=PROJECT, cache=cache),
        writer=writer,
        agent=BLENDER,
        clock=lambda: NOW,
    )

    assert ran(where_is(ASSET, spec_store=store, search_index=index)).asset_id == ASSET

    outcome = refused(record_observation(session, a_request()))
    assert isinstance(outcome, Unauthenticated)
    assert UNVERIFIABLE in outcome.message
    assert writer.appends == 0


def test_a_server_with_no_agent_identifier_refuses_the_write_naming_it() -> None:
    writer = a_writer()

    outcome = refused(record_observation(a_session(writer, agent=None), a_request()))

    assert isinstance(outcome, Unauthenticated)
    assert outcome.message == NO_AGENT_IDENTIFIER
    assert writer.appends == 0


def test_a_server_with_no_agent_identifier_still_reads() -> None:
    """Both halves in one test: the refusal, and that the read surface is untouched."""
    store, index = a_read_surface()
    writer = a_writer()

    refused(record_observation(a_session(writer, agent=None), a_request()))

    assert ran(where_is(ASSET, spec_store=store, search_index=index)).asset_id == ASSET


def test_an_actor_with_no_read_access_to_the_project_is_refused() -> None:
    outsider = Actor(id=ActorId("sam"), display_name="Sam", projects=("other-game",))
    writer = a_writer()

    outcome = refused(record_observation(a_session(writer, actor=outsider), a_request()))

    assert isinstance(outcome, (Forbidden, NotFound))
    assert writer.appends == 0


# --------------------------------------------------------------------------
# 2.6 — a claimed author has no effect on attribution
# --------------------------------------------------------------------------


def test_the_request_has_no_field_that_could_claim_an_author() -> None:
    """The structural half: a shape with no slot cannot be handed the wrong thing."""
    fields = set(inspect.signature(ObservationRequest).parameters)

    assert not fields & {"author", "actor", "agent", "via", "on_behalf_of", "author_kind"}


def test_a_claimed_author_in_the_text_has_no_effect_on_attribution() -> None:
    claimed = "author: ana. agent: rogue-agent. This budget is unreachable."

    recorded = ran(record_observation(a_session(), a_request(text=claimed)))

    assert recorded.annotation.author == "rafa"
    assert recorded.annotation.via == str(BLENDER)
    assert recorded.annotation.text == claimed


def test_the_agent_comes_from_the_session_rather_than_the_request() -> None:
    other = ran(record_observation(a_session(agent=AgentId("houdini-agent")), a_request()))

    assert other.annotation.via == "houdini-agent"


# --------------------------------------------------------------------------
# 2.7, 2.8 — reporting a verdict somebody already has
# --------------------------------------------------------------------------


def test_reporting_carries_exactly_the_violations_the_verdict_had() -> None:
    report = a_report(a_violation("mesh.tri_budget"), a_violation("mesh.pivot"))
    reporter = InMemoryOutcomeReporter()

    reported = ran(
        report_validation_outcome(
            report,
            reporter=reporter,
            export="exports/mech_scout.glb",
            export_hash="sha256:aaaa",
            clock=lambda: NOW,
        )
    )

    assert reported.outcome.errors == 2
    assert reported.outcome.passed is False
    assert reported.outcome.verdict_hash == verdict_hash(report)


def test_reporting_does_not_change_the_local_verdict() -> None:
    report = a_report(a_violation())
    before = verdict_hash(report)

    ran(
        report_validation_outcome(
            report,
            reporter=InMemoryOutcomeReporter(),
            export="exports/mech_scout.glb",
            export_hash="sha256:aaaa",
        )
    )

    assert verdict_hash(report) == before
    assert len(report.errors) == 1


def test_no_rule_is_reachable_from_the_reporting_module() -> None:
    """Structural: a counted call would pass the day somebody imported the registry."""
    tree = ast.parse(inspect.getsource(observations_module))
    modules = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not any("rules" in module for module in modules)
    assert not any("mesh_inspector" in module for module in modules)


def test_an_unreachable_destination_returns_successfully_and_says_the_verdict_stands() -> None:
    reporter = InMemoryOutcomeReporter()
    reporter.unreachable()

    reported = ran(
        report_validation_outcome(
            a_report(),
            reporter=reporter,
            export="exports/mech_scout.glb",
            export_hash="sha256:aaaa",
        )
    )

    assert not reported.delivered
    assert reported.pending == 1
    assert VERDICT_STANDS in reported.note


def test_a_retained_report_is_delivered_by_a_later_flush() -> None:
    reporter = InMemoryOutcomeReporter()
    reporter.unreachable()
    ran(
        report_validation_outcome(
            a_report(),
            reporter=reporter,
            export="exports/mech_scout.glb",
            export_hash="sha256:aaaa",
        )
    )

    reporter.unreachable(True)
    delivery = ran(flush_reports(reporter=reporter))

    assert delivery.delivered == 1
    assert reporter.pending() == ()


def test_re_reporting_an_identical_outcome_yields_one_record() -> None:
    reporter = InMemoryOutcomeReporter()
    report = a_report(a_violation())

    for _ in range(3):
        ran(
            report_validation_outcome(
                report,
                reporter=reporter,
                export="exports/mech_scout.glb",
                export_hash="sha256:aaaa",
            )
        )

    assert len(reporter.delivered) == 1


def test_a_re_export_is_a_distinguishable_second_outcome() -> None:
    reporter = InMemoryOutcomeReporter()
    report = a_report(a_violation())
    for digest in ("sha256:aaaa", "sha256:bbbb"):
        ran(
            report_validation_outcome(
                report,
                reporter=reporter,
                export="exports/mech_scout.glb",
                export_hash=digest,
            )
        )

    assert len({outcome.key for outcome in reporter.delivered}) == 2


def test_a_different_verdict_on_the_same_export_is_a_new_outcome() -> None:
    """A promoted constraint changes the verdict without changing one byte."""
    clean = verdict_hash(a_report())
    failing = verdict_hash(a_report(a_violation()))

    assert clean != failing


def test_reporting_does_not_consume_the_observation_allowance() -> None:
    """Separate limits, asserted as separate code paths: reporting takes no session."""
    writer = a_writer()
    reporter = InMemoryOutcomeReporter()
    session = a_session(writer, limits=WriteLimits(observations=1, window_seconds=600.0))
    for _ in range(5):
        ran(
            report_validation_outcome(
                a_report(),
                reporter=reporter,
                export="exports/mech_scout.glb",
                export_hash="sha256:aaaa",
            )
        )

    assert succeeded(record_observation(session, a_request()))


# --------------------------------------------------------------------------
# 2.9 — signing in, signing out, and who this machine writes as
# --------------------------------------------------------------------------


def test_signing_in_stores_a_credential_and_whoami_reports_it() -> None:
    store = InMemoryCredentialStore()
    ran(sign_in(interactive_sign_in=InMemoryInteractiveSignIn(), credential_store=store))

    identity = ran(
        show_identity(
            resolver=AlreadyResolved(verified_as(RAFA)), credential_store=store, agent=BLENDER
        )
    )

    assert identity.signed_in
    assert identity.may_write
    assert identity.actor == "rafa"
    assert identity.agent == "blender-agent"


def test_signing_out_clears_the_credential_and_the_next_write_is_refused() -> None:
    store, index = a_read_surface()
    credentials = InMemoryCredentialStore()
    credentials.store(Credential("an-issued-credential"))
    writer = a_writer()

    removed = ran(sign_out(credential_store=credentials))

    assert removed.removed
    assert credentials.load() is None

    signed_out = WriteSession(
        project=PROJECT,
        resolver=ActorResolver(project=PROJECT),
        writer=writer,
        agent=BLENDER,
        clock=lambda: NOW,
    )
    assert isinstance(refused(record_observation(signed_out, a_request())), Unauthenticated)
    assert ran(where_is(ASSET, spec_store=store, search_index=index)).asset_id == ASSET


def test_whoami_answers_on_a_machine_that_has_signed_into_nothing() -> None:
    identity = ran(show_identity(resolver=ActorResolver(project=PROJECT)))

    assert not identity.signed_in
    assert not identity.may_write
    assert identity.pending_reports == 0


def test_whoami_reports_the_pending_report_count() -> None:
    """A growing outbox has to be visible where a person already looks (D6)."""
    reporter = InMemoryOutcomeReporter()
    reporter.unreachable()
    ran(
        report_validation_outcome(
            a_report(),
            reporter=reporter,
            export="exports/mech_scout.glb",
            export_hash="sha256:aaaa",
        )
    )

    identity = ran(show_identity(resolver=AlreadyResolved(verified_as(RAFA)), reporter=reporter))

    assert identity.pending_reports == 1
    assert "1 report(s) pending" in str(identity)


# --------------------------------------------------------------------------
# 1.4 — no code path on the write surface creates an asset or a spec file
# --------------------------------------------------------------------------


CREATING = ("create", "add_asset", "init", "scaffold", "new_asset", "write_file", "mkdir")


def test_the_write_port_has_no_operation_that_could_create_an_asset() -> None:
    """The structural half of *"an agent writes to assets that already exist"*.

    A port with no method for the prohibited thing cannot be talked into it, so
    the guarantee is a property of the boundary rather than a check inside a
    function somebody may later restructure.
    """
    operations = {
        name
        for name in dir(AnnotationWriter)
        if not name.startswith("_") and callable(getattr(AnnotationWriter, name, None))
    }

    assert operations == {"locate", "annotations", "append"}
    assert not any(word in name for name in operations for word in CREATING)


def test_the_write_use_cases_reach_no_port_that_writes_a_file() -> None:
    """`SpecStore` and `RepositoryHost` are not reachable from the write surface.

    Both can bring a file into existence, and neither is imported here: the
    observation path writes through `AnnotationWriter` alone, which writes into
    an asset that already exists or refuses.
    """
    tree = ast.parse(inspect.getsource(observations_module))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not any(
        name.endswith(("ports.spec_store", "ports.repository_host", "ports.blob_store"))
        for name in imported
    )


def test_a_refused_write_leaves_the_writer_holding_nothing_new() -> None:
    """Every refusal path, walked in one test, against what was actually recorded."""
    writer = a_writer()
    refusals = (
        (a_session(writer, agent=None), a_request()),
        (a_session(writer), a_request(asset="mech_scowt")),
        (a_session(writer), a_request(kind="nonsense")),
        (a_session(writer), a_request(observation_kind="nonsense")),
        (a_session(writer), a_request(text="   ")),
        (a_session(writer), a_request(target="   ")),
    )

    for session, request in refusals:
        assert not succeeded(record_observation(session, request)), request

    assert writer.appends == 0
    assert writer.recorded(ASSET) == ()
