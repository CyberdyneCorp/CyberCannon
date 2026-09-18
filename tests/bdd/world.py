"""What a scenario has on the table (task 4.2).

Its own module rather than a conftest: `tests/bdd/steps/` also has a conftest,
so `from conftest import ...` would resolve to whichever of the two pytest
inserted into `sys.path` first.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class World:
    """The fakes a scenario runs against, and whatever its GIVENs named.

    Actors, projects and assets are recorded by the identifier the scenario
    named them with. The value is that identifier until the domain types exist;
    a capability's steps replace it with the real object when they have one.
    """

    fakes: Mapping[str, Any]
    actors: dict[str, object] = field(default_factory=dict)
    projects: dict[str, object] = field(default_factory=dict)
    assets: dict[str, object] = field(default_factory=dict)
