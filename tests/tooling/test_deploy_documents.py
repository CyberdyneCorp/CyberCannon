"""Task 1.5 — `deploy/README.md` and the settings model name the same variables.

D1 accepts a cost in so many words: *"four places to keep environment lists
honest"*. This is how that cost is paid. A deployment document that drifts from
the code is worse than no document, because the person reading it at three in
the morning believes it — and the failure mode it hides is exactly the one D3
was meant to make loud: a variable nobody set.

So the check runs in both directions. A setting the service declares and the
document does not mention fails the build; a `CANON_` variable the document
describes and nothing reads fails it too. The second direction matters more than
it looks: a removed setting leaves a paragraph behind, and a paragraph about a
variable that does nothing is how an operator ends up setting it and wondering
why nothing changed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cybercanon.adapters.wiring.configuration import OPTIONAL, REQUIRED, SECRETS, SETTINGS

DEPLOY = Path("deploy") / "README.md"
WEB_CONFIG = Path("apps") / "cybercanon" / "web" / "src" / "lib" / "config.ts"

VARIABLE = re.compile(r"`(CANON_[A-Z0-9_]+)`")
PUBLIC_VARIABLE = re.compile(r"\b(PUBLIC_[A-Z0-9_]+)\b")

REQUIRED_HEADING = "### `api` — required"
OPTIONAL_HEADING = "### `api` — optional"
WEB_HEADING = "### `web` — required"


@pytest.fixture(scope="module")
def document(repo_root: Path) -> str:
    text = (repo_root / DEPLOY).read_text(encoding="utf-8")
    assert text.strip(), f"{DEPLOY} is where every deployed variable is written down"
    return text


def _section(document: str, heading: str) -> str:
    """One `###` section of the document, up to the next heading."""
    start = document.index(heading) + len(heading)
    rest = document[start:]
    end = rest.find("\n### ")
    return rest if end < 0 else rest[:end]


def _named(text: str) -> set[str]:
    return set(VARIABLE.findall(text))


# --------------------------------------------------------------------------
# The two directions
# --------------------------------------------------------------------------


def test_every_required_variable_is_documented(document: str) -> None:
    undocumented = set(REQUIRED) - _named(_section(document, REQUIRED_HEADING))

    assert not undocumented, (
        f"these variables are required to start the service and {DEPLOY} does not "
        f"list them: {sorted(undocumented)}"
    )


def test_every_optional_variable_is_documented(document: str) -> None:
    undocumented = set(OPTIONAL) - _named(_section(document, OPTIONAL_HEADING))

    assert not undocumented, f"{DEPLOY} omits the optional settings {sorted(undocumented)}"


def test_the_document_describes_nothing_the_service_does_not_read(document: str) -> None:
    declared = {setting.name for setting in SETTINGS}
    invented = _named(document) - declared

    assert not invented, (
        f"{DEPLOY} describes variables nothing reads: {sorted(invented)}. A "
        "paragraph about a variable that does nothing is how an operator ends up "
        "setting it and wondering why nothing changed"
    )


def test_a_required_variable_is_not_also_listed_as_optional(document: str) -> None:
    """The two tables are the answer to "will it start without this"."""
    assert not (_named(_section(document, OPTIONAL_HEADING)) & set(REQUIRED))


def test_every_secret_is_marked_as_one(document: str) -> None:
    """An operator has to know which values may never be pasted into a ticket."""
    for name in SECRETS:
        row = next(line for line in document.splitlines() if f"`{name}`" in line)
        assert "●" in row, f"{name} is a secret and {DEPLOY} does not mark it as one"


# --------------------------------------------------------------------------
# The web application reads its own, and it is documented in the same place
# --------------------------------------------------------------------------


def test_the_web_applications_variables_are_documented(repo_root: Path, document: str) -> None:
    read = PUBLIC_VARIABLE.findall((repo_root / WEB_CONFIG).read_text(encoding="utf-8"))
    documented = PUBLIC_VARIABLE.findall(_section(document, WEB_HEADING))

    assert read, f"{WEB_CONFIG} is where the application reads its endpoint"
    assert set(read) <= set(documented), f"{DEPLOY} omits {sorted(set(read) - set(documented))}"


def test_the_document_names_the_four_deployed_applications(document: str) -> None:
    """The hosted inventory is exactly four, and this is where it is written down."""
    for application in ("`api`", "`web`", "`postgres`", "`minio`"):
        assert application in document


def test_the_document_states_that_the_command_line_and_agent_server_are_not_hosted(
    document: str,
) -> None:
    assert "not here" in document
    assert "stdio" in document
