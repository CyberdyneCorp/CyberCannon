"""Task 1.2a — the justfile carries the baseline recipes, and `check` runs them.

openspec/project.md: "there is exactly one way to run any operation, and it is a
`just` recipe", and `just check` is "everything CI runs, in CI's order".
"""

from __future__ import annotations

from canon_lint.justfile import Recipe, parse_justfile

BASELINE_RECIPES = ("setup", "check", "test", "lint", "imports", "complexity", "spec")

# The recipes `check` must pull in. `setup` is deliberately absent: it installs,
# it does not verify.
CHECKS_UNDER_CHECK = ("lint", "imports", "complexity", "test", "spec")


def test_baseline_recipes_exist(recipes: dict[str, Recipe]) -> None:
    missing = [name for name in BASELINE_RECIPES if name not in recipes]
    assert not missing, f"justfile is missing baseline recipes: {missing}"


def test_check_runs_every_check_recipe(recipes: dict[str, Recipe]) -> None:
    missing = [name for name in CHECKS_UNDER_CHECK if name not in recipes["check"].dependencies]
    assert not missing, (
        f"`just check` does not run {missing}; it is specified as everything CI runs, "
        "so a check outside it is a check CI will never run."
    )


def test_check_only_delegates(recipes: dict[str, Recipe]) -> None:
    """`check` composes recipes; it never grows a command of its own."""
    assert recipes["check"].body == (), (
        "`just check` should be a list of dependencies, so every check it runs is "
        f"independently runnable; found inline commands: {recipes['check'].body}"
    )


def test_every_dependency_resolves(recipes: dict[str, Recipe]) -> None:
    for recipe in recipes.values():
        unknown = [dep for dep in recipe.dependencies if dep not in recipes]
        assert not unknown, f"recipe `{recipe.name}` depends on unknown recipes {unknown}"


def test_parser_reads_dependencies_and_bodies() -> None:
    """Regression guard: the parser these tests rely on must not silently return {}."""
    parsed = parse_justfile(
        'var := "x"\n'
        "# a comment\n"
        "check: lint test\n"
        "\n"
        "lint:\n"
        "    uv run ruff check .\n"
        "\n"
        "test *args:\n"
        "    uv run pytest {{ args }}\n"
    )
    assert set(parsed) == {"check", "lint", "test"}
    assert parsed["check"].dependencies == ("lint", "test")
    assert parsed["lint"].body == ("uv run ruff check .",)
    assert parsed["test"].body == ("uv run pytest {{ args }}",)


def test_the_web_artifact_is_built_before_the_suite_that_runs_it(
    recipes: dict[str, Recipe],
) -> None:
    """`web-check` builds the application; an integration suite then starts it.

    tests/integration/test_web_readiness_process.py runs the built artifact —
    the `node build` the web image's command runs — to ask a *process* whether
    it is ready with no API answering (task 2.4, D10). That is only a real
    assertion while the build exists when `test` runs, so the order is asserted
    here rather than relied on.
    """
    order = recipes["check"].dependencies

    assert "web-check" in order and "test" in order
    assert order.index("web-check") < order.index("test"), (
        "`just check` runs `test` before `web-check`, so the web artifact is not "
        "built when the suite that starts it runs, and that suite silently skips"
    )
