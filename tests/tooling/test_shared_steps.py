"""Task 4.3 — the shared step module holds universal steps and nothing else.

The shared module is visible to every scenario in the repository, so a phrase
that means something to one capability and something else to another does its
damage here. Two gates, and the second is the one that matters: the patterns
are checked for capability vocabulary, and then run over all 657 scenarios'
step lines to prove they only ever match a bare existence line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from canon_bdd import generator, steps
from canon_bdd.implemented import STEPS_DIR
from canon_bdd.specs import CapabilitySpec, iter_scenarios

SHARED_MODULE = STEPS_DIR / "conftest.py"

UNIVERSAL_NOUNS = ("actor", "project", "asset")
"""What a universal step may be about: the three things every capability shares."""

ALLOWED_WORDS = frozenset({"a", "an", "the", "actor", "project", "asset", "named", "name", "p"})
"""Every word a universal pattern may contain, regex group names included."""

EXISTENCE_LINE = re.compile(r"^an? (?:actor|project|asset)(?: named)? [`\"'][^`\"']+[`\"']$")
"""A bare existence GIVEN: it names the thing and qualifies it in no way."""

SUBJECT = re.compile(r"^an? (?P<noun>actor|project|asset)\b")
WORD = re.compile(r"[a-z]+")


@pytest.fixture(scope="module")
def shared(repo_root: Path) -> tuple[steps.StepDeclaration, ...]:
    return steps.declarations_in(repo_root / SHARED_MODULE)


@pytest.fixture(scope="module")
def specs(repo_root: Path) -> tuple[CapabilitySpec, ...]:
    return generator.load_specs(repo_root)


@pytest.fixture(scope="module")
def spec_step_lines(specs: tuple[CapabilitySpec, ...]) -> tuple[str, ...]:
    """Every GIVEN/WHEN/THEN line in the corpus, verbatim."""
    return tuple(step.text for _, _, scenario in iter_scenarios(specs) for step in scenario.steps)


@pytest.fixture(scope="module")
def capability_vocabulary(specs: tuple[CapabilitySpec, ...]) -> frozenset[str]:
    """Every word a capability or change slug is made of — minus the universal ones."""
    words = {
        word
        for spec in specs
        for slug in (spec.capability, spec.change)
        for word in slug.split("-")
    }
    return frozenset(words - ALLOWED_WORDS)


# --------------------------------------------------------------------------
# The module holds three universal GIVENs, and their phrasing stays universal
# --------------------------------------------------------------------------


def test_the_shared_module_declares_only_given_steps(
    shared: tuple[steps.StepDeclaration, ...],
) -> None:
    """A universal WHEN or THEN is a behaviour, and behaviour belongs to a capability."""
    offenders = [
        f"{item.keyword} at line {item.line}" for item in shared if item.keyword != "given"
    ]
    assert not offenders, offenders


def test_every_shared_pattern_can_be_read(shared: tuple[steps.StepDeclaration, ...]) -> None:
    """A computed phrase would put the shared module beyond this gate's reach."""
    unreadable = [item.line for item in shared if not item.is_readable]
    assert not unreadable, f"step phrases at lines {unreadable} are not literal strings"


def test_there_is_one_universal_step_per_universal_noun(
    shared: tuple[steps.StepDeclaration, ...],
) -> None:
    subjects = [_subject(item.pattern) for item in shared]
    assert sorted(subjects) == sorted(UNIVERSAL_NOUNS), (
        f"the shared module declares steps about {subjects}; the universal steps "
        f"are exactly one per {UNIVERSAL_NOUNS} (task 4.3)"
    )


def test_no_capability_vocabulary_leaks_into_the_shared_module(
    shared: tuple[steps.StepDeclaration, ...], capability_vocabulary: frozenset[str]
) -> None:
    leaks = {
        item.line: sorted(capability_vocabulary.intersection(WORD.findall(item.pattern.lower())))
        for item in shared
        if capability_vocabulary.intersection(WORD.findall(item.pattern.lower()))
    }
    assert not leaks, (
        f"capability vocabulary in the shared step module: {leaks}. A step that "
        "speaks one capability's language belongs in tests/bdd/steps/<capability>.py."
    )


# --------------------------------------------------------------------------
# And what they actually match, across the whole corpus
# --------------------------------------------------------------------------


def test_a_shared_step_only_ever_matches_a_bare_existence_line(
    shared: tuple[steps.StepDeclaration, ...], spec_step_lines: tuple[str, ...]
) -> None:
    """The anti-leak gate, run against all 657 scenarios rather than an example."""
    captured = [
        f"{item.pattern!r} matches {line!r}"
        for item in shared
        for line in spec_step_lines
        if re.match(item.pattern, line) and not EXISTENCE_LINE.match(line)
    ]
    assert not captured, (
        "a universal step matched a qualified spec line:\n  "
        + "\n  ".join(captured)
        + "\nA qualified GIVEN belongs to the capability that qualified it."
    )


def test_the_universal_steps_match_the_existence_lines_the_specs_do_write(
    shared: tuple[steps.StepDeclaration, ...], spec_step_lines: tuple[str, ...]
) -> None:
    """Non-vacuity: these steps are reachable from the real corpus, not decoration."""
    matched = [
        line for line in spec_step_lines if any(re.match(item.pattern, line) for item in shared)
    ]
    assert matched, "no spec line matches any universal step; the phrasings have drifted apart"


def _subject(pattern: str) -> str:
    match = SUBJECT.match(pattern)
    assert match is not None, f"{pattern!r} does not start by naming one of {UNIVERSAL_NOUNS}"
    return match.group("noun")
