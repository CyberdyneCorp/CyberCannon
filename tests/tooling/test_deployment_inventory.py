"""Tasks 8.1 and 8.5 — the deployed set is exactly four, and that is checkable.

`deployment-operations` states the hosted inventory as a closed set and then
says the quiet part out loud: *"no other component SHALL be added to the hosted
inventory without a specification change"*, and *"the `canon` command line and
the agent server SHALL NOT be deployed as network-reachable services, in any
environment, including behind authentication or on a private network."*

An exclusion is the one kind of requirement nobody notices breaking. Nothing
fails when a fifth application appears; somebody just wanted the agent surface
reachable from a laptop on a Tuesday. So the declaration is data —
`deploy/coolify.yaml` — and this suite is the gate over it: the real manifest
conforms, and each way of breaking the requirement is fabricated and asserted to
be **reported, naming the specification**, rather than merely counted.

The other half is D1's accepted cost, *"four places to keep environment lists
honest"*: the variables each application is given, the two health paths, the
volumes, the stop grace period and the pre-deploy command are all checked
against what the service actually declares and reads. A manifest that drifted
from the code would be the deployment-document failure one layer down —
believed, and wrong.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from canon_deploy import inventory as declared
from canon_deploy.__main__ import main, web_variables
from cybercanon.adapters.wiring.configuration import OPTIONAL, REQUIRED

MANIFEST = declared.MANIFEST_PATH

SPECIFIED = ("the HTTP API service", "the web application", "the index database", "the blob store")
"""The four, in the specification's own words. The manifest names them as keys."""


@pytest.fixture(scope="module")
def manifest(repo_root: Path) -> declared.Inventory:
    return declared.load(repo_root / MANIFEST)


def _findings(repo_root: Path, inventory: declared.Inventory) -> tuple[str, ...]:
    return declared.findings(
        inventory,
        required=REQUIRED,
        optional=OPTIONAL,
        web_required=web_variables(repo_root),
    )


def _rewritten(repo_root: Path, tmp_path: Path, change) -> declared.Inventory:
    """The real manifest with one thing broken, loaded back through the reader."""
    yaml = YAML(typ="safe")
    document = yaml.load((repo_root / MANIFEST).read_text(encoding="utf-8"))
    change(document)
    buffer = io.StringIO()
    yaml.dump(document, buffer)
    broken = tmp_path / "coolify.yaml"
    broken.write_text(buffer.getvalue(), encoding="utf-8")
    return declared.load(broken)


# --------------------------------------------------------------------------
# The declaration this repository ships
# --------------------------------------------------------------------------


def test_the_manifest_is_committed(repo_root: Path) -> None:
    """The check has to be answerable from a checkout, platform or no platform."""
    assert (repo_root / MANIFEST).is_file(), f"{MANIFEST} is where the four are declared"


def test_the_declared_deployment_conforms(repo_root: Path, manifest: declared.Inventory) -> None:
    found = _findings(repo_root, manifest)

    assert not found, "the declared deployment does not conform:\n" + "\n".join(found)


def test_the_inventory_is_exactly_the_four_specified(manifest: declared.Inventory) -> None:
    assert set(manifest.components) == set(declared.COMPONENTS)
    assert len(manifest.applications) == len(SPECIFIED)


def test_each_component_is_individually_deployable(manifest: declared.Inventory) -> None:
    """*"individually deployable, individually restartable"* — so one entry each."""
    names = [one.name for one in manifest.applications]

    assert len(set(names)) == len(names), "two applications share a name"
    for one in manifest.applications:
        assert one.dockerfile or one.managed, f"{one.name} is neither built nor managed"


def test_the_two_unhosted_surfaces_are_recorded_with_a_reason(
    manifest: declared.Inventory,
) -> None:
    for name in declared.NEVER_HOSTED:
        assert manifest.never_hosted.get(name), f"{name} is not recorded as deliberately absent"
    assert "stdio" in manifest.never_hosted[declared.AGENT_SERVER]


def test_the_model_endpoint_is_inside_the_deployment_network(
    manifest: declared.Inventory,
) -> None:
    """Task 8.2's first half: concept art is unreleased intellectual property."""
    api = manifest.by_component(declared.HTTP_API)

    assert api is not None
    assert manifest.host_suffix in api.values["CANON_LLM_BASE_URL"]


# --------------------------------------------------------------------------
# Each way of breaking it, fabricated
# --------------------------------------------------------------------------


def test_a_fifth_application_is_reported_as_a_specification_change(
    repo_root: Path, tmp_path: Path
) -> None:
    def add_one(document: dict) -> None:
        document["applications"]["search"] = {
            "component": "semantic_search",
            "host": f"search.{document['host_suffix']}",
            "dockerfile": "deploy/search.Dockerfile",
        }

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, add_one))

    assert any("semantic_search" in line and "specification change" in line for line in found)


def test_hosting_the_agent_server_is_reported_as_non_conforming(
    repo_root: Path, tmp_path: Path
) -> None:
    """The scenario, as a check: a deployment that exposes it is rejected."""

    def host_the_agent(document: dict) -> None:
        document["applications"]["mcp"] = {
            "component": declared.AGENT_SERVER,
            "host": f"mcp.{document['host_suffix']}",
            "dockerfile": "deploy/mcp.Dockerfile",
        }

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, host_the_agent))

    assert any(declared.AGENT_SERVER in line for line in found)
    assert any("local-first" in line for line in found)


def test_a_missing_volume_is_reported(repo_root: Path, tmp_path: Path) -> None:
    def forget_the_volume(document: dict) -> None:
        document["applications"]["postgres"]["volumes"] = []

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, forget_the_volume))

    assert any(declared.INDEX_DATABASE in line and "redeploy" in line for line in found)


def test_a_liveness_probe_pointed_at_readiness_is_reported(repo_root: Path, tmp_path: Path) -> None:
    def conflate(document: dict) -> None:
        document["applications"]["api"]["health"]["liveness"] = "/readyz"

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, conflate))

    assert any("restart probe" in line for line in found)


def test_a_stop_grace_period_that_is_not_the_drain_window_is_reported(
    repo_root: Path, tmp_path: Path
) -> None:
    def shorten(document: dict) -> None:
        document["applications"]["api"]["health"]["stop_grace_period"] = "10"

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, shorten))

    assert any("write-back budget" in line for line in found)


def test_migrating_at_start_is_reported(repo_root: Path, tmp_path: Path) -> None:
    def migrate_on_boot(document: dict) -> None:
        document["applications"]["api"]["command"] = "python -m cybercanon.api.migrate && serve"

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, migrate_on_boot))

    assert any("once per instance" in line for line in found)


def test_a_variable_nothing_reads_is_reported(repo_root: Path, tmp_path: Path) -> None:
    def invent(document: dict) -> None:
        document["applications"]["api"]["environment"]["required"].append("CANON_INVENTED")

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, invent))

    assert any("CANON_INVENTED" in line for line in found)


def test_a_variable_the_service_reads_and_is_not_given_is_reported(
    repo_root: Path, tmp_path: Path
) -> None:
    def forget(document: dict) -> None:
        document["applications"]["api"]["environment"]["required"].remove("CANON_DATABASE_URL")

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, forget))

    assert any("CANON_DATABASE_URL" in line for line in found)


def test_a_model_endpoint_outside_the_network_is_reported(repo_root: Path, tmp_path: Path) -> None:
    def send_it_away(document: dict) -> None:
        document["applications"]["api"]["environment"]["values"]["CANON_LLM_BASE_URL"] = (
            "https://api.openai.com/v1"
        )

    found = _findings(repo_root, _rewritten(repo_root, tmp_path, send_it_away))

    assert any("on the premises" in line for line in found)


# --------------------------------------------------------------------------
# The command an operator and a pipeline run
# --------------------------------------------------------------------------


def test_the_check_command_passes_over_the_real_manifest(repo_root: Path) -> None:
    out = io.StringIO()

    code = main(["check", "--root", str(repo_root)], out)

    assert code == 0, out.getvalue()
    assert "four components" in out.getvalue()


def test_the_check_command_exits_non_zero_over_a_broken_one(
    repo_root: Path, tmp_path: Path
) -> None:
    yaml = YAML(typ="safe")
    document = yaml.load((repo_root / MANIFEST).read_text(encoding="utf-8"))
    document["applications"].pop("minio")
    broken = tmp_path / "coolify.yaml"
    buffer = io.StringIO()
    yaml.dump(document, buffer)
    broken.write_text(buffer.getvalue(), encoding="utf-8")
    out = io.StringIO()

    code = main(["check", "--root", str(repo_root), "--manifest", str(broken)], out)

    assert code != 0
    assert declared.BLOB_STORE in out.getvalue()
