"""The shared step module — universal steps only (task 4.3, D4).

A step here is visible to every capability's scenarios, which is precisely why
almost nothing belongs here: a global step namespace is how a BDD suite rots,
with a step phrased for one capability silently matching another's scenario and
asserting the wrong thing. Three steps qualify, because they carry no
capability's vocabulary at all — an actor exists, a project exists, an asset
exists.

The patterns are anchored and accept only a quoted or backticked identifier, so
``an asset `mech_scout``` matches while ``an asset with a triangle budget of
12000`` does not: a qualified GIVEN belongs to the capability that qualified it.

`tests/tooling/test_shared_steps.py` enforces both halves of that — the step
list is an allow-list, and no capability vocabulary may appear in a pattern.

The ``world`` these steps write to is the fixture in ``tests/bdd/conftest.py``.
"""

from __future__ import annotations

from pytest_bdd import given, parsers

ACTOR = r"an actor(?: named)? [`\"'](?P<name>[^`\"']+)[`\"']$"
PROJECT = r"a project(?: named)? [`\"'](?P<name>[^`\"']+)[`\"']$"
ASSET = r"an asset(?: named)? [`\"'](?P<name>[^`\"']+)[`\"']$"

UNIVERSAL_PATTERNS = (ACTOR, PROJECT, ASSET)


@given(parsers.re(ACTOR))
def _an_actor_exists(world, name: str) -> None:
    world.actors[name] = name


@given(parsers.re(PROJECT))
def _a_project_exists(world, name: str) -> None:
    world.projects[name] = name


@given(parsers.re(ASSET))
def _an_asset_exists(world, name: str) -> None:
    world.assets[name] = name
