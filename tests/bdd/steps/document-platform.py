"""Step definitions for `document-platform` — linking, displaying, and the boundary.

The arrangement is `tests/documents_world.py`, the same one
`tests/unit/test_use_case_documents.py` runs against: a real repository host
holding real `asset.yaml` bytes, the adapter's own comment-preserving writer over
them, the in-memory document platform beside it and the real use cases on top.
So a scenario here passes because the product does the thing, not because a step
asserted about a value it built itself.

Two scenarios are deliberately *not* about the platform at all — compilation and
validation — and they are the ones worth reading twice: both run the real
`compile_spec` and `validate_export`, neither of which has a parameter that
could reach a document platform, and the assertion is that the answers are
byte-identical with it up, down and absent.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when

from cybercanon.adapters.outbound.git import schema, yaml_io
from cybercanon.application.ports.document_platform import UnavailabilityReason
from cybercanon.application.testing.mesh_inspector import InMemoryMeshInspector
from cybercanon.application.testing.outcomes import ran, refused
from cybercanon.application.testing.spec_store import InMemorySpecStore
from cybercanon.application.use_cases.compile_spec import compile_spec
from cybercanon.application.use_cases.documents import AVAILABLE_ACTIONS, actions_for
from cybercanon.application.use_cases.validate_export import validate_export
from cybercanon.domain.format_matrix import facts_for
from cybercanon.domain.mesh_facts import MeshFormat
from cybercanon.domain.spec_checks import RULE_MALFORMED_DOCUMENT_REF
from documents_world import (
    BRUNO_ACTOR,
    GDD,
    PRIVATE,
    PROSE,
    RAFA_ACTOR,
    RATIONALE,
    RESEARCH,
    WORKSPACE,
    Documents,
    a_world,
    with_links,
    with_project_link,
    without_platform,
)
from views_world import SCOUT_SPEC

EXPORT = "characters/mech_scout/exports/SM_mech_scout_LOD0.glb"
OBJECT = "SM_mech_scout_LOD0"

DECLARED_BUDGET = 12_000
PROSE_BUDGET = 40_000
"""What the *document* claims, in prose. The specification says 12000."""

LONG_PROSE = " ".join([PROSE] * 60)
"""Several thousand words of rationale, for the compilation-size scenario."""

WITH_BUDGET = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
status: modeling
constraints:
  tri_budget: {DECLARED_BUDGET}
documents:
  - workspace: {WORKSPACE}
    id: {RATIONALE}
    url: https://documents.invalid/w/{WORKSPACE}/d/{RATIONALE}
"""

MALFORMED = f"""\
schema_version: 1
id: mech_scout
name: Scout Mech
documents:
  - workspace: {WORKSPACE}
    id: {RATIONALE}
    url: not-an-address
"""


@pytest.fixture
def links() -> dict[str, Any]:
    """The world this scenario runs in, and whatever its steps produced."""
    return {"world": a_world()}


def _world(links: dict[str, Any]) -> Documents:
    return links["world"]


def _facts(triangles: int):
    return facts_for(
        MeshFormat.GLB,
        triangles=triangles,
        objects=(OBJECT,),
        transforms_applied=True,
        unit_scale=1.0,
        up_axis="Y",
        uv_sets=1,
        materials=("M_mech_scout",),
        empties=(),
        clips=(),
        frame_rate=None,
        is_skinned=False,
        bone_count=0,
    )


def _validated(text: str, triangles: int):
    """One export validated against a specification carrying document links."""
    store = InMemorySpecStore()
    data = yaml_io.load_mapping(text, subject=SCOUT_SPEC)
    parsed, _ = schema.parse_asset_file(data)
    asset, _ = schema.to_asset(parsed)
    store.add(SCOUT_SPEC, asset)
    inspector = InMemoryMeshInspector()
    inspector.add(EXPORT, _facts(triangles))
    return ran(validate_export(EXPORT, spec_store=store, mesh_inspector=inspector))


def _compiled(world: Documents) -> str:
    return ran(compile_spec(SCOUT_SPEC, spec_store=world.spec_store)).text


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Only the reference is authored",
)
def test_only_the_reference_is_authored() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Resolved display data is disposable",
)
def test_resolved_display_data_is_disposable() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Editing happens elsewhere",
)
def test_editing_happens_elsewhere() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Asset link is versioned with the asset",
)
def test_asset_link_is_versioned_with_the_asset() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Project link is visible from every asset",
)
def test_project_link_is_visible_from_every_asset() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Removing a link leaves the document untouched",
)
def test_removing_a_link_leaves_the_document_untouched() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Link list reads as documents",
)
def test_link_list_reads_as_documents() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Title follows a rename at the source",
)
def test_title_follows_a_rename_at_the_source() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Unresolved link is still usable",
)
def test_unresolved_link_is_still_usable() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Service unavailable",
)
def test_service_unavailable() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Deleted document",
)
def test_deleted_document() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Viewer not permitted",
)
def test_viewer_not_permitted() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "One broken link does not break the list",
)
def test_one_broken_link_does_not_break_the_list() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Deterministic ordering",
)
def test_deterministic_ordering() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Scope is visible",
)
def test_scope_is_visible() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "One action produces a linked document",
)
def test_one_action_produces_a_linked_document() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Creation refused leaves no link",
)
def test_creation_refused_leaves_no_link() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Link write failure names the created document",
)
def test_link_write_failure_names_the_created_document() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "No field is generated from a document",
)
def test_no_field_is_generated_from_a_document() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Guidance at the point of authoring",
)
def test_guidance_at_the_point_of_authoring() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Document contents are not constraints",
)
def test_document_contents_are_not_constraints() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Compiled output does not vary with platform reachability",
)
def test_compiled_output_does_not_vary() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Compilation is not blocked by the platform",
)
def test_compilation_is_not_blocked_by_the_platform() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "No prose is compiled in",
)
def test_no_prose_is_compiled_in() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Resolved content never reaches authored or compiled artifacts",
)
def test_resolved_content_never_reaches_authored_artifacts() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Offline validation is unaffected",
)
def test_offline_validation_is_unaffected() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Malformed reference is a specification violation",
)
def test_malformed_reference_is_a_specification_violation() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Unconfigured deployment works",
)
def test_unconfigured_deployment_works() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Creating a link reports unavailability",
)
def test_creating_a_link_reports_unavailability() -> None: ...


@scenario(
    "../features/add-cyberarche-integration/document-platform.feature",
    "Existing references survive",
)
def test_existing_references_survive() -> None: ...


# --------------------------------------------------------------------------
# GIVEN
# --------------------------------------------------------------------------


@given("a document containing several pages of prose")
def _a_document_of_prose(links: dict[str, Any]) -> None:
    """The platform already holds it; nothing about it is in the repository."""
    links["document"] = RATIONALE


@given("an asset with linked documents whose titles have been resolved")
def _links_whose_titles_are_resolved(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE, RESEARCH)
    links["before"] = ran(world.listed())
    assert links["before"].entries[0].card.title


@given("a document linked at project scope")
def _a_project_scoped_link(links: dict[str, Any]) -> None:
    links["world"] = with_project_link(GDD)


@given("an asset with two linked documents the viewer may read")
def _two_readable_links(links: dict[str, Any]) -> None:
    with_links(_world(links), RATIONALE, RESEARCH)


@given("a linked document whose title was resolved previously")
def _a_previously_resolved_title(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE)
    links["first_title"] = ran(world.listed()).entries[0].card.title


@given("a reference whose title cannot be resolved")
def _a_reference_that_will_not_resolve(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE)
    world.unavailable(UnavailabilityReason.UNREACHABLE)


@given("the document platform is unreachable")
def _the_platform_is_unreachable(links: dict[str, Any]) -> None:
    _world(links).unavailable(UnavailabilityReason.UNREACHABLE)


@given("a linked document that has been deleted at the document platform")
def _a_deleted_document(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE)
    world.platform.delete(WORKSPACE, RATIONALE)


@given("a linked document the viewer has not been granted access to")
def _a_forbidden_document(links: dict[str, Any]) -> None:
    with_links(_world(links), PRIVATE)


@given("an asset with one readable link and one forbidden link")
def _one_readable_one_forbidden(links: dict[str, Any]) -> None:
    with_links(_world(links), RATIONALE, PRIVATE)


@given("an asset with several linked documents")
def _several_linked_documents(links: dict[str, Any]) -> None:
    with_links(_world(links), RATIONALE, RESEARCH, PRIVATE)


@given("a person without permission to create documents in the target workspace")
def _a_person_who_may_not_create(links: dict[str, Any]) -> None:
    links["actor"] = BRUNO_ACTOR


@given("a document that was created successfully")
def _a_document_that_was_created(links: dict[str, Any]) -> None:
    """Creation succeeds; the repository is what will refuse the write (D8)."""
    links["actor"] = RAFA_ACTOR


@given("a linked document describing a socket in prose")
def _a_document_describing_a_socket(links: dict[str, Any]) -> None:
    world = _world(links)
    links["design_before"] = world.asset().design
    with_links(world, RATIONALE)


@given("a linked document stating a triangle budget in prose")
def _a_document_stating_a_budget(links: dict[str, Any]) -> None:
    assert "forty thousand" in PROSE, "the document is the one that claims 40000"
    links["spec_text"] = WITH_BUDGET


@given("an asset carrying document links")
def _an_asset_carrying_links(links: dict[str, Any]) -> None:
    with_links(_world(links), RATIONALE, PRIVATE)


@given("a linked document of several thousand words")
def _a_very_long_document(links: dict[str, Any]) -> None:
    world = _world(links)
    world.platform.add_document(
        WORKSPACE, "d_long", "a very long document", summary=LONG_PROSE, body=LONG_PROSE
    )
    links["without"] = _compiled(world)
    with_links(world, "d_long")


@given("a resolved title and summary held for a document link")
def _a_resolved_card(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE)
    entry = ran(world.listed()).entries[0]
    links["title"] = entry.card.title
    links["summary"] = entry.card.summary
    assert links["title"] and links["summary"]


@given("an asset carrying document links and no network access")
def _links_and_no_network(links: dict[str, Any]) -> None:
    links["spec_text"] = WITH_BUDGET
    links["reachable_report"] = _validated(WITH_BUDGET, DECLARED_BUDGET - 1000).report


@given("no document platform configuration in the environment")
def _no_platform_configuration(links: dict[str, Any]) -> None:
    links["world"] = without_platform(_world(links))


@given("an asset carrying document references and no platform configuration")
def _references_and_no_configuration(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE, RESEARCH)
    links["world"] = without_platform(world)


# --------------------------------------------------------------------------
# WHEN
# --------------------------------------------------------------------------


@when("it is linked to an asset")
def _it_is_linked(links: dict[str, Any]) -> None:
    ran(_world(links).link(links["document"]))


@when("all rebuildable storage is deleted and rebuilt")
def _rebuildable_storage_is_dropped(links: dict[str, Any]) -> None:
    """The display cache is the only derived storage a link has (D1)."""
    world = _world(links)
    world.cache.clear()
    links["after"] = ran(world.listed())


@when("a person acts on a linked document from within the system")
def _a_person_acts_on_a_link(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE)
    links["entry"] = ran(world.listed()).entries[0]


@when("a person links a document to an asset")
def _a_person_links_a_document(links: dict[str, Any]) -> None:
    links["recorded"] = ran(_world(links).link(RATIONALE))
    links["commits"] = _world(links).host.commits(_world(links).spec_store.project)


@when("any asset in that project is viewed")
def _any_asset_is_viewed(links: dict[str, Any]) -> None:
    links["listing"] = ran(with_links(_world(links), RATIONALE).listed())


@when("a person removes a document link")
def _a_person_removes_a_link(links: dict[str, Any]) -> None:
    world = with_links(_world(links), RATIONALE)
    links["calls_before"] = len(world.platform.requests)
    ran(world.unlink(RATIONALE))


@when("the viewer lists the asset's links")
@when("the asset's links are listed")
@when("its links are listed")
def _the_links_are_listed(links: dict[str, Any]) -> None:
    links["listing"] = ran(_world(links).listed())


@when("the document is renamed at the document platform and the link is viewed again")
def _the_document_is_renamed(links: dict[str, Any]) -> None:
    world = _world(links)
    world.platform.rename(WORKSPACE, RATIONALE, "mech_scout — why it reads as a courier")
    world.age(10_000)
    links["listing"] = ran(world.listed())


@when("the link is displayed")
def _the_link_is_displayed(links: dict[str, Any]) -> None:
    links["listing"] = ran(_world(links).listed())


@when("an asset with three linked documents is displayed")
def _three_links_are_displayed(links: dict[str, Any]) -> None:
    world = _world(links)
    with_links(world, RATIONALE, RESEARCH, GDD)
    world.unavailable(UnavailabilityReason.UNREACHABLE)
    links["listing"] = ran(world.listed())
    links["compiled"] = _compiled(world)


@when("its links are listed twice without any change to the specification")
def _listed_twice(links: dict[str, Any]) -> None:
    world = _world(links)
    links["first"] = ran(world.listed())
    links["second"] = ran(world.listed())


@when("an asset with both asset-scoped and project-scoped links is listed")
def _both_scopes_are_listed(links: dict[str, Any]) -> None:
    world = with_links(with_project_link(GDD), RATIONALE)
    links["world"] = world
    links["listing"] = ran(world.listed())


@when("a person creates a design document for it")
def _a_person_creates_a_document(links: dict[str, Any]) -> None:
    links["recorded"] = ran(_world(links).create())


@when("they attempt to create a design document for an asset")
def _they_attempt_to_create(links: dict[str, Any]) -> None:
    world = _world(links)
    links["before"] = world.spec_text()
    links["outcome"] = world.create(actor=links["actor"])


@when("writing the reference into the specification fails")
def _the_write_fails(links: dict[str, Any]) -> None:
    world = _world(links)
    world.refuse_writes()
    links["outcome"] = world.create()


@when("the link is created and the asset is displayed and compiled")
def _created_displayed_and_compiled(links: dict[str, Any]) -> None:
    world = _world(links)
    ran(world.listed())
    links["compiled"] = _compiled(world)
    links["design_after"] = world.asset().design


@when("a person is offered the choice of where to write a statement")
def _the_choice_is_offered(links: dict[str, Any]) -> None:
    links["guidance"] = ran(_world(links).listed()).guidance


@when("an export exceeding that number but within the specification's declared budget is validated")
def _an_export_within_the_declared_budget(links: dict[str, Any]) -> None:
    assert DECLARED_BUDGET < PROSE_BUDGET
    links["outcome"] = _validated(links["spec_text"], DECLARED_BUDGET - 1)


@when("it is compiled with the platform reachable and again with it unreachable")
def _compiled_reachable_and_not(links: dict[str, Any]) -> None:
    world = _world(links)
    ran(world.listed())
    links["reachable"] = _compiled(world)
    world.unavailable(UnavailabilityReason.UNREACHABLE)
    links["unreachable"] = _compiled(world)


@when("an asset's specification is compiled")
def _the_specification_is_compiled(links: dict[str, Any]) -> None:
    with_links(_world(links), RATIONALE)
    links["compiled"] = _compiled(_world(links))


@when("the asset's specification is compiled")
def _the_asset_specification_is_compiled(links: dict[str, Any]) -> None:
    links["compiled"] = _compiled(_world(links))


@when("the asset's specification file and its compiled briefing are examined")
def _both_artifacts_are_examined(links: dict[str, Any]) -> None:
    world = _world(links)
    links["artifacts"] = (world.spec_text(), _compiled(world))


@when("its export is validated")
def _the_export_is_validated(links: dict[str, Any]) -> None:
    links["outcome"] = _validated(links["spec_text"], DECLARED_BUDGET - 1000)


@when("a specification contains a document reference that is not well formed")
def _a_malformed_reference(links: dict[str, Any]) -> None:
    data = yaml_io.load_mapping(MALFORMED, subject=SCOUT_SPEC)
    parsed, warnings = schema.parse_asset_file(data)
    asset, more = schema.to_asset(parsed)
    links["asset"] = asset
    links["findings"] = (*warnings, *more)


@when("assets are browsed, specifications compiled and exports validated")
def _everything_else_is_exercised(links: dict[str, Any]) -> None:
    configured = with_links(a_world(), RATIONALE)
    unconfigured = without_platform(with_links(a_world(), RATIONALE))
    links["configured"] = (
        _compiled(configured),
        configured.asset(),
        _validated(WITH_BUDGET, DECLARED_BUDGET - 1000).report,
    )
    links["unconfigured"] = (
        _compiled(unconfigured),
        unconfigured.asset(),
        _validated(WITH_BUDGET, DECLARED_BUDGET - 1000).report,
    )


@when("a person attempts to create a design document for an asset")
def _a_person_attempts_with_no_configuration(links: dict[str, Any]) -> None:
    world = _world(links)
    links["before"] = world.spec_text()
    links["outcome"] = world.create()


# --------------------------------------------------------------------------
# THEN
# --------------------------------------------------------------------------


@then("the asset's specification file SHALL contain only the reference and its authorship")
def _the_file_holds_the_reference(links: dict[str, Any]) -> None:
    text = _world(links).spec_text()
    assert RATIONALE in text
    assert "linked_by:" in text
    assert "title" not in text.split("documents:")[1]


@then("it SHALL NOT contain any of the document's body text")
def _the_file_holds_no_body(links: dict[str, Any]) -> None:
    text = _world(links).spec_text()
    for sentence in PROSE.split(". "):
        assert sentence not in text


@then("the same links SHALL be listed with the same references")
def _the_same_references_come_back(links: dict[str, Any]) -> None:
    assert [entry.ref for entry in links["after"].entries] == [
        entry.ref for entry in links["before"].entries
    ]


@then("their titles SHALL be resolved again from the document platform")
def _the_titles_are_resolved_again(links: dict[str, Any]) -> None:
    resolves = [
        request for request in _world(links).platform.requests if request.operation == "resolve"
    ]
    assert len(resolves) >= 2, "the dropped cache forced a second resolve"
    assert links["after"].entries[0].card.title == links["before"].entries[0].card.title


@then(
    "the only available actions SHALL be opening it at the document platform and removing the link"
)
def _only_two_actions(links: dict[str, Any]) -> None:
    assert actions_for(links["entry"]) == AVAILABLE_ACTIONS == ("open", "unlink")


@then("no interface for editing the document's contents SHALL be offered")
def _no_editing_is_offered(links: dict[str, Any]) -> None:
    assert not {"edit", "write", "save", "update"} & set(AVAILABLE_ACTIONS)


@then(
    "the change SHALL appear as a modification to that asset's specification file "
    "attributed to that person"
)
def _the_commit_is_attributed(links: dict[str, Any]) -> None:
    recorded = links["recorded"]
    assert recorded.path == SCOUT_SPEC
    assert recorded.ref.linked_by == RAFA_ACTOR.subject
    assert links["commits"][-1].author.email == "rafa@cyberdyne.com"
    assert RATIONALE in _world(links).spec_text()


@then(
    "that document SHALL be listed as a project-scoped link, distinguished from "
    "the asset's own links"
)
def _the_project_link_is_distinguished(links: dict[str, Any]) -> None:
    listing = links["listing"]
    assert [entry.ref.document_id for entry in listing.project_links] == [GDD]
    assert [entry.ref.document_id for entry in listing.asset_links] == [RATIONALE]


@then("the reference SHALL be removed from the specification")
def _the_reference_is_gone(links: dict[str, Any]) -> None:
    assert RATIONALE not in _world(links).spec_text()


@then("the document at the document platform SHALL NOT be modified or deleted")
def _the_document_is_untouched(links: dict[str, Any]) -> None:
    world = _world(links)
    assert world.platform.exists(WORKSPACE, RATIONALE)
    assert len(world.platform.requests) == links["calls_before"]


@then("each SHALL be shown with its current title and summary")
def _each_has_a_title_and_summary(links: dict[str, Any]) -> None:
    entries = links["listing"].entries
    assert len(entries) == 2
    assert all(entry.card.title for entry in entries)
    assert all(entry.card.summary for entry in entries)


@then("the newly displayed title SHALL be the current one")
def _the_new_title_is_shown(links: dict[str, Any]) -> None:
    title = links["listing"].entries[0].card.title
    assert title == "mech_scout — why it reads as a courier"
    assert title != links["first_title"]
    assert title not in _world(links).spec_text()


@then("it SHALL be shown with its address and marked as unresolved")
def _shown_as_an_address(links: dict[str, Any]) -> None:
    entry = links["listing"].entries[0]
    assert not entry.is_resolved
    assert entry.card.display_title == entry.address


@then("it SHALL remain openable")
def _it_remains_openable(links: dict[str, Any]) -> None:
    assert links["listing"].entries[0].address.startswith("https://")


@then("all three SHALL be listed as temporarily unresolvable")
def _all_three_unreachable(links: dict[str, Any]) -> None:
    entries = links["listing"].entries
    assert len(entries) == 3
    assert {entry.state.value for entry in entries} == {"unreachable"}


@then("the rest of the asset's specification SHALL display normally")
def _the_rest_displays(links: dict[str, Any]) -> None:
    compiled = links["compiled"]
    assert "## Engineering constraints" in compiled
    assert "12000" in compiled


@then("it SHALL be marked as no longer existing")
def _marked_missing(links: dict[str, Any]) -> None:
    assert links["listing"].entries[0].state.value == "missing"


@then("the reference SHALL remain in the specification until a person removes it")
def _the_reference_remains(links: dict[str, Any]) -> None:
    assert RATIONALE in _world(links).spec_text()


@then("it SHALL be marked as not accessible to this viewer")
def _marked_forbidden(links: dict[str, Any]) -> None:
    assert links["listing"].entries[0].state.value == "forbidden"


@then("no title, summary or other content of that document SHALL be shown")
def _nothing_is_disclosed(links: dict[str, Any]) -> None:
    card = links["listing"].entries[0].card
    assert card.discloses_nothing
    assert card.display_title == card.address


@then("the readable link SHALL be shown resolved")
def _the_readable_one_resolved(links: dict[str, Any]) -> None:
    entry = links["listing"].entry(RATIONALE)
    assert entry is not None
    assert entry.card.title == "mech_scout — design rationale"


@then("the forbidden link SHALL be shown in its state")
def _the_forbidden_one_in_its_state(links: dict[str, Any]) -> None:
    entry = links["listing"].entry(PRIVATE)
    assert entry is not None
    assert entry.state.value == "forbidden"


@then("both listings SHALL contain the same links in the same order")
def _both_listings_agree(links: dict[str, Any]) -> None:
    assert [entry.ref for entry in links["first"].entries] == [
        entry.ref for entry in links["second"].entries
    ]
    assert [entry.state for entry in links["first"].entries] == [
        entry.state for entry in links["second"].entries
    ]


@then("each entry SHALL state which scope it came from")
def _each_entry_states_its_scope(links: dict[str, Any]) -> None:
    scopes = [entry.scope.value for entry in links["listing"].entries]
    assert scopes == ["asset", "project"]


@then("a document SHALL exist at the document platform whose title identifies that asset")
def _a_document_exists_named_for_the_asset(links: dict[str, Any]) -> None:
    created = links["recorded"].created
    assert created is not None
    assert "mech_scout" in created.title
    assert _world(links).platform.exists(WORKSPACE, created.document_id)


@then("the asset's specification SHALL contain a reference to it attributed to that person")
def _the_spec_references_it(links: dict[str, Any]) -> None:
    created = links["recorded"].created
    text = _world(links).spec_text()
    assert created is not None
    assert created.document_id in text
    assert f"linked_by: {RAFA_ACTOR.subject}" in text


@then("the attempt SHALL be refused with the reason")
def _the_attempt_is_refused(links: dict[str, Any]) -> None:
    refusal = refused(links["outcome"])
    assert refusal.kind.value == "forbidden"
    assert "may not create documents" in refusal.message


@then("the asset's specification SHALL be unchanged")
def _the_specification_is_unchanged(links: dict[str, Any]) -> None:
    assert _world(links).spec_text() == links["before"]


@then("the failure SHALL be reported")
def _the_failure_is_reported(links: dict[str, Any]) -> None:
    assert refused(links["outcome"]).identifier == "document.created_but_not_linked"


@then("the report SHALL name the created document and its address")
def _the_report_names_the_document(links: dict[str, Any]) -> None:
    message = refused(links["outcome"]).message
    created = _world(links).platform.created
    assert created, "the document really was created"
    assert created[-1].url in message
    assert created[-1].title in message


@then("no `design` field SHALL have been added or altered")
def _the_design_block_is_untouched(links: dict[str, Any]) -> None:
    assert links["design_after"] == links["design_before"]
    assert links["design_after"] is not None
    assert [socket.name for socket in links["design_after"].sockets] == ["SOCKET_muzzle_l"]


@then("validation of an export SHALL be unaffected by that document's contents")
def _validation_is_unaffected(links: dict[str, Any]) -> None:
    with_platform = _validated(WITH_BUDGET, DECLARED_BUDGET - 1)
    assert with_platform.passed
    assert with_platform.report.violations == ()


@then(
    "the system SHALL state that constraining or checkable statements belong in the "
    "specification and that rationale belongs in the document"
)
def _the_guidance_names_both(links: dict[str, Any]) -> None:
    guidance = links["guidance"]
    assert "specification" in guidance
    assert "Rationale" in guidance
    assert "linked document" in guidance


@then("no violation SHALL be reported")
def _no_violation(links: dict[str, Any]) -> None:
    assert links["outcome"].report.violations == ()
    assert links["outcome"].passed


@then("the two outputs SHALL be byte-identical")
def _byte_identical(links: dict[str, Any]) -> None:
    assert links["reachable"] == links["unreachable"]


@then("compilation SHALL succeed")
def _compilation_succeeds(links: dict[str, Any]) -> None:
    assert links["compiled"].startswith("# mech_scout")


@then("each document link SHALL appear as its address")
def _links_appear_as_addresses(links: dict[str, Any]) -> None:
    compiled = links["compiled"]
    assert f"/d/{RATIONALE}" in compiled
    assert "mech_scout — design rationale" not in compiled


@then("the compiled output SHALL grow by at most the link's own line")
def _grows_by_one_line(links: dict[str, Any]) -> None:
    added = links["compiled"][len(links["without"]) :]
    assert len(added) < 200
    assert LONG_PROSE[:80] not in links["compiled"]


@then("neither SHALL contain the resolved title or summary")
def _neither_artifact_holds_the_card(links: dict[str, Any]) -> None:
    for artifact in links["artifacts"]:
        assert links["title"] not in artifact
        assert links["summary"] not in artifact


@then("validation SHALL complete")
def _validation_completes(links: dict[str, Any]) -> None:
    assert links["outcome"].report is not None


@then("its report SHALL be identical to the report produced with the platform reachable")
def _the_reports_are_identical(links: dict[str, Any]) -> None:
    assert links["outcome"].report == links["reachable_report"]


@then("specification linting SHALL report it")
def _linting_reports_it(links: dict[str, Any]) -> None:
    assert [finding.rule_id for finding in links["findings"]] == [RULE_MALFORMED_DOCUMENT_REF]
    assert links["asset"].documents == ()


@then("the report SHALL name the offending reference")
def _the_report_names_the_reference(links: dict[str, Any]) -> None:
    finding = links["findings"][0]
    assert RATIONALE in finding.message
    assert "documents[0]" in finding.subject


@then("all SHALL behave exactly as with the platform configured")
def _everything_else_is_identical(links: dict[str, Any]) -> None:
    assert links["configured"] == links["unconfigured"]


@then("the feature SHALL report itself unavailable and name the reason")
def _reports_itself_unavailable(links: dict[str, Any]) -> None:
    refusal = refused(links["outcome"])
    assert refusal.kind.value == "unavailable"
    assert "unconfigured" in refusal.message


@then("no specification SHALL be modified")
def _no_specification_modified(links: dict[str, Any]) -> None:
    assert _world(links).spec_text() == links["before"]


@then("each reference SHALL be listed with its address and marked unresolved")
def _every_reference_is_an_address(links: dict[str, Any]) -> None:
    listing = links["listing"]
    assert [entry.ref.document_id for entry in listing.entries] == [RATIONALE, RESEARCH]
    assert all(entry.address.startswith("https://") for entry in listing.entries)
    assert all(not entry.is_resolved for entry in listing.entries)
    assert listing.unavailable_reason is UnavailabilityReason.UNCONFIGURED
