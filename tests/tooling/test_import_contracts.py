"""Task 1.3 — the layering contracts, and proof the domain-purity one bites.

D10 makes the layering structural rather than conventional. `just imports` runs
`lint-imports` against the real codebase; these tests assert the contracts are
declared and that the custom `stdlib_only` contract actually fails when the
domain reaches for a third-party package — a contract that can never break is
indistinguishable from no contract at all.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from grimp import ImportGraph

from canon_lint.contracts import StdlibOnlyContract

DOMAIN = "cybercanon.domain"


def _graph(*imports: tuple[str, str]) -> ImportGraph:
    """Build the shape grimp produces for real: every ancestor package present."""
    graph = ImportGraph()
    for importer, imported in imports:
        _add_package(graph, importer)
        if imported.startswith("cybercanon"):
            _add_package(graph, imported)
        else:
            graph.add_module(imported, is_squashed=True)
        graph.add_import(
            importer=importer,
            imported=imported,
            line_number=1,
            line_contents=f"import {imported}",
        )
    return graph


def _add_package(graph: ImportGraph, module: str) -> None:
    parts = module.split(".")
    for depth in range(1, len(parts) + 1):
        graph.add_module(".".join(parts[:depth]))


def _contract() -> StdlibOnlyContract:
    return StdlibOnlyContract(
        name="The domain imports no third-party package",
        session_options={"root_packages": [DOMAIN]},
        contract_options={"modules": [DOMAIN]},
    )


def test_stdlib_imports_are_allowed() -> None:
    graph = _graph((f"{DOMAIN}.rules", "dataclasses"), (f"{DOMAIN}.rules", "enum"))

    assert _contract().check(graph, verbose=False).kept


def test_internal_imports_are_allowed() -> None:
    """Domain -> application is the layers contract's business, not this one's."""
    graph = _graph((f"{DOMAIN}.rules", "cybercanon.application.ports"))

    assert _contract().check(graph, verbose=False).kept


def test_a_third_party_import_breaks_the_contract() -> None:
    graph = _graph((f"{DOMAIN}.spec", "pydantic"), (f"{DOMAIN}.rules", "dataclasses"))

    check = _contract().check(graph, verbose=False)

    assert not check.kept
    assert [(o["importer"], o["imported"]) for o in check.metadata["offenders"]] == [
        (f"{DOMAIN}.spec", "pydantic")
    ]


def test_a_third_party_import_by_the_package_root_breaks_the_contract() -> None:
    graph = _graph((DOMAIN, "trimesh"))

    check = _contract().check(graph, verbose=False)

    assert not check.kept
    assert check.metadata["offenders"][0]["line_numbers"] == (1,)


def _by_type(repo_root: Path) -> dict[str, list[dict[str, object]]]:
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    declared: dict[str, list[dict[str, object]]] = {}
    for contract in config["tool"]["importlinter"]["contracts"]:
        declared.setdefault(contract["type"], []).append(contract)
    return declared


def test_the_declared_contracts_cover_every_clause_of_d10(repo_root: Path) -> None:
    by_type = _by_type(repo_root)

    (layers,) = by_type["layers"]
    (stdlib_only,) = by_type["stdlib_only"]
    assert layers["layers"] == [
        "cybercanon.adapters",
        "cybercanon.application",
        "cybercanon.domain",
    ]
    assert [contract["source_modules"] for contract in by_type["forbidden"]] == [
        ["cybercanon.adapters.inbound"],
        ["cybercanon.adapters.inbound.http"],
    ]
    assert all(
        contract["forbidden_modules"] == ["cybercanon.adapters.outbound"]
        for contract in by_type["forbidden"]
    )
    assert stdlib_only["modules"] == ["cybercanon.domain"]


def test_the_http_adapter_is_named_by_a_contract_of_its_own(repo_root: Path) -> None:
    """Task 1.2 — so a broken layering names the surface that broke it.

    The package-wide contract already covers it; this one exists so the failure
    reads "The HTTP adapter must not import outbound adapters" rather than
    naming the whole inbound package, on the surface the product has the most to
    lose from.
    """
    named = {contract["name"] for contract in _by_type(repo_root)["forbidden"]}

    assert "The HTTP adapter must not import outbound adapters" in named
