# Step definitions

One module per capability (D4): `tests/bdd/steps/<capability>.py`, named exactly
as the capability directory under `openspec/changes/*/specs/`. A step phrased for
one capability must not match another capability's scenario, and a global step
namespace is how that rots, so the only shared module is the universal one
(task 4.3: an actor exists, a project exists, an asset exists).

A scenario *executes* when a step module binds it:

```python
from pytest_bdd import given, scenario, then, when

@scenario("../features/add-asset-spec-and-validator/asset-validation.feature", "Over budget")
def test_over_budget() -> None: ...
```

Three rules the harness depends on:

1. **The feature path and the scenario name are literal strings.** The gates read
   the bindings from the source without importing it, so a computed name reads as
   *not executing* and fails the build rather than quietly claiming coverage.
2. **Never edit a `.feature`.** They are generated from the spec deltas by
   `just gen-features`, and `just features` fails on any hand edit.
3. **A scenario with no binding must be listed in `tests/bdd/pending.txt`**, the
   single reviewed exception. Nothing is ever skipped silently.

`scenarios("../features/<change>/<capability>.feature")` binds every scenario in
one feature at once — correct only when the capability is fully implemented,
since pytest-bdd then fails on any scenario still missing a step.

## The shared module and the fixtures

`conftest.py` beside this file is the one shared step module (task 4.3). It
holds three universal GIVENs and nothing else — an actor, a project or an asset
exists — each anchored to a quoted or backticked identifier, so a qualified line
like `an asset with a triangle budget of 12000` belongs to the capability that
qualified it. `tests/tooling/test_shared_steps.py` enforces that against all 657
scenarios, and `tests/tooling/test_step_scoping.py` proves the runner keeps one
capability's steps out of another's scenario.

Two fixtures come from `tests/bdd/conftest.py`:

* `fakes` — a fresh in-memory fake per port, built by
  `cybercanon.application.testing.build_fakes`, the same constructor the unit
  suite calls. A change that adds a port adds its fake to `FAKE_FACTORIES` and
  every scenario has it.
* `world` — those fakes plus whatever the universal GIVENs named.
