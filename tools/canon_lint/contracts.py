"""Custom import-linter contract types for CyberCanon.

``StdlibOnlyContract`` implements the third clause of D10:

    ``libs/cybercanon/domain`` MUST NOT import any third-party package.

An enumerated ``forbidden`` contract cannot express that: it is a deny-list, so
the day someone adds a dependency nobody remembered to list, the contract passes
while the rule is broken. This contract inverts it into an allow-list of exactly
two things — the standard library and the project's own root package — which is
what D10 actually says.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

from grimp import ImportGraph
from importlinter import Contract, ContractCheck, fields, output


class StdlibOnlyContract(Contract):
    """Check that the given modules import nothing outside the standard library.

    Configuration options:
        - modules:            Modules (treated as packages) that must stay pure.
        - internal_packages:  Root packages counted as first-party and therefore
                              allowed. Defaults to the root package of each
                              module under check.
    """

    type_name = "stdlib_only"

    modules = fields.ListField(subfield=fields.ModuleField())
    internal_packages = fields.ListField(subfield=fields.StringField(), required=False)

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        allowed = set(sys.stdlib_module_names) | self._internal_roots()
        offenders = [
            {"importer": importer, "imported": imported, "line_numbers": lines}
            for importer, imported in self._imports_under_check(graph)
            if _root_of(imported) not in allowed
            for lines in [_line_numbers(graph, importer, imported)]
        ]
        output.verbose_print(verbose, f"Checked {len(self.modules)} module(s) for stdlib purity.")
        return ContractCheck(kept=not offenders, metadata={"offenders": offenders})

    def render_broken_contract(self, check: ContractCheck) -> None:
        for offender in check.metadata["offenders"]:
            lines = ", ".join(str(number) for number in offender["line_numbers"]) or "?"
            output.print_error(
                f"{offender['importer']} imports the third-party package "
                f"{offender['imported']} (line {lines}).",
                bold=False,
            )
        output.new_line()

    def _internal_roots(self) -> set[str]:
        if self.internal_packages:
            return set(self.internal_packages)
        return {_root_of(str(module)) for module in self.modules}

    def _imports_under_check(self, graph: ImportGraph) -> Iterator[tuple[str, str]]:
        for module in self.modules:
            name = str(module)
            for member in {name, *graph.find_descendants(name)}:
                for imported in graph.find_modules_directly_imported_by(member):
                    yield member, imported


def _root_of(module_name: str) -> str:
    return module_name.split(".")[0]


def _line_numbers(graph: ImportGraph, importer: str, imported: str) -> tuple[int, ...]:
    details = graph.get_import_details(importer=importer, imported=imported)
    return tuple(detail["line_number"] for detail in details)
