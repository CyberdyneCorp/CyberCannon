"""The declared deployment: four applications, and the two that are never hosted.

`deployment-operations` requires that the hosted inventory be *exactly* four
components and that adding a fifth be a specification change. That is a claim
about a set, so the set is declared as data in `deploy/coolify.yaml` and
:mod:`canon_deploy.inventory` is what reads it back against the specification
and against the settings the service actually declares.
"""

from canon_deploy.inventory import (
    COMPONENTS,
    MANIFEST_PATH,
    NEVER_HOSTED,
    Application,
    Health,
    Inventory,
    Volume,
    findings,
    load,
)

__all__ = [
    "COMPONENTS",
    "MANIFEST_PATH",
    "NEVER_HOSTED",
    "Application",
    "Health",
    "Inventory",
    "Volume",
    "findings",
    "load",
]
