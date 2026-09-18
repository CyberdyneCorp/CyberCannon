"""The harness plugin: one marker per test layer, and `--tag` for capabilities.

Loaded for every pytest run through ``addopts`` in ``pyproject.toml``.

* **Layer markers.** A test's layer is its directory — ``tests/unit`` is unit,
  ``tests/bdd`` is BDD, ``tests/conformance`` is port conformance, ``tests/e2e``
  is end-to-end, ``tests/tooling`` verifies the build itself. Marking by
  location means a test cannot be filed in one layer and marked as another.
* **`--tag`.** D5 puts the change, the capability and the spec path on every
  generated feature, so ``just test-bdd --tag asset-validation`` runs exactly one
  capability's scenarios. pytest's own ``-m`` cannot express a tag containing a
  hyphen or a colon, so the selection lives here.
* **The traceability report.** Task 3.4 wants the pending count written on
  every ``just check``. It is computed from the spec deltas, the step modules
  and the pending list — not from what this session happened to run — so it is
  written once collection is complete, which lets the gate tests assert in the
  same session that the file on disk is current.
* **`pytest_bdd_apply_tag`.** Those tags are traceability metadata, not pytest
  markers: turning ``@spec:openspec/...`` into a marker would collide with
  ``--strict-markers`` and say nothing useful. The hook claims them so pytest-bdd
  does not.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from canon_bdd import generator, implemented, pending, traceability
from canon_bdd.pending import PendingListError
from canon_bdd.specs import SpecParseError

LAYERS = ("unit", "bdd", "conformance", "e2e", "tooling")
TESTS_DIR = "tests"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--tag",
        action="append",
        default=[],
        metavar="TAG",
        help=(
            "Run only scenarios carrying this generated tag — a capability "
            "(asset-validation), a change (add-mcp-writes) or a full tag "
            "(capability:asset-validation). Repeatable."
        ),
    )


@pytest.hookimpl(tryfirst=True)
def pytest_bdd_apply_tag(tag: str, function: Any) -> bool | None:
    """Claim the generated traceability tags; leave anything else to pytest-bdd.

    ``tryfirst`` matters: the hook is firstresult, and pytest-bdd's own
    implementation always answers, so a later-registered plugin would never see
    the tag and ``@spec:openspec/...`` would reach ``--strict-markers``.
    """
    return True if ":" in tag else None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    rootdir = Path(str(config.rootpath))
    for item in items:
        _mark_layer(item, rootdir)
    _select_by_tag(config, items, tuple(config.getoption("--tag")))


def _mark_layer(item: pytest.Item, rootdir: Path) -> None:
    layer = _layer_of(Path(str(item.path)), rootdir)
    if layer is not None:
        item.add_marker(layer)


def _layer_of(path: Path, rootdir: Path) -> str | None:
    if not path.is_relative_to(rootdir):
        return None
    parts = path.relative_to(rootdir).parts
    if len(parts) < 2 or parts[0] != TESTS_DIR:
        return None
    return parts[1] if parts[1] in LAYERS else None


def _select_by_tag(
    config: pytest.Config, items: list[pytest.Item], wanted: tuple[str, ...]
) -> None:
    if not wanted:
        return
    selected = [item for item in items if _matches(_tags_of(item), wanted)]
    deselected = [item for item in items if item not in selected]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def _tags_of(item: pytest.Item) -> set[str]:
    """The feature, rule and scenario tags pytest-bdd recorded on a bound test."""
    scenario = getattr(getattr(item, "function", None), "__scenario__", None)
    if scenario is None:
        return set()
    rule = getattr(scenario, "rule", None)
    return set(scenario.feature.tags) | set(scenario.tags) | set(rule.tags if rule else ())


def _matches(tags: Iterable[str], wanted: tuple[str, ...]) -> bool:
    values = set(tags) | {tag.split(":", 1)[1] for tag in tags if ":" in tag}
    return any(tag in values for tag in wanted)


def pytest_collection_finish(session: pytest.Session) -> None:
    """Write the per-capability traceability report (task 3.4)."""
    write_report(Path(str(session.config.rootpath)))


def write_report(repo_root: Path) -> Path | None:
    """The report, or None when this root holds no spec deltas or cannot be read.

    A spec that will not parse is not silenced here: the generator recipe and the
    gate tests both fail on it, loudly and with the file name.
    """
    if not (repo_root / "openspec").is_dir():
        return None
    try:
        specs = generator.load_specs(repo_root)
        entries = pending.load(repo_root / pending.PENDING_PATH)
    except (SpecParseError, PendingListError):
        return None
    bindings = implemented.discover(repo_root / implemented.STEPS_DIR)
    statuses = traceability.classify(specs, bindings, entries)
    path = repo_root / traceability.REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(traceability.render_report(statuses), encoding="utf-8")
    return path
