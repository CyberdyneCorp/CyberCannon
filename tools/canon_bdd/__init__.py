"""The BDD harness: spec deltas in, executable Gherkin and traceability out.

The spec deltas under ``openspec/changes/*/specs/*/spec.md`` are the source of
truth for behaviour. This package reads them (:mod:`canon_bdd.specs`), renders
them as Gherkin (:mod:`canon_bdd.gherkin`, :mod:`canon_bdd.generator`), and
pins the generated scenarios to the code that executes them
(:mod:`canon_bdd.implemented`, :mod:`canon_bdd.pending`,
:mod:`canon_bdd.traceability`).

Nothing here is product code: it lives under ``tools/`` so the hexagonal core
never depends on it.
"""

from __future__ import annotations
