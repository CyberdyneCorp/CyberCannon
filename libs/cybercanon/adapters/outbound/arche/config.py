"""What this deployment needs to reach CyberArche, and nothing it can do without.

Configuration is environment variables with no file fallback, exactly as it is
everywhere else in this product (`openspec/project.md`): Coolify supplies
configuration as environment, and a file that disagrees with it is a deployment
behaving differently from how it is described.

Five variables, and the shape of the set is D4: **absent or incomplete
configuration is not an error, it is the null adapter**. A deployment that never
sets `CANON_ARCHE_ENABLED` behaves exactly as it did before this change existed,
which is what makes the whole integration removable.

The address a link opens at is configuration rather than something this adapter
derives, because it is *another application's routing*. Guessing it would mean
every CyberArche release could silently turn every stored link into a 404, and
the guess would live in a value git keeps forever.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

ENABLED = "CANON_ARCHE_ENABLED"
BASE_URL = "CANON_ARCHE_BASE_URL"
DEFAULT_WORKSPACE = "CANON_ARCHE_DEFAULT_WORKSPACE"
TIMEOUT = "CANON_ARCHE_TIMEOUT_S"
WEB_URL = "CANON_ARCHE_WEB_URL"

VARIABLES: tuple[str, ...] = (ENABLED, BASE_URL, DEFAULT_WORKSPACE, TIMEOUT, WEB_URL)
"""Every variable this adapter reads, so a deployment document can be checked."""

DEFAULT_TIMEOUT = timedelta(seconds=5)
"""The failure budget a call gets before it is *not this time* (D5)."""

DOCUMENT_PATH = "/w/{workspace}/d/{document_id}"
"""Where a document is opened in the CyberArche web application.

A default rather than a constant: it is another application's routing, and a
studio running a different build changes one environment variable instead of
waiting for a release here.
"""

TRUE_VALUES = ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ArcheSettings:
    """The document platform's address, workspace and failure budget."""

    enabled: bool = False
    base_url: str = ""
    default_workspace: str = ""
    web_url: str = ""
    timeout: timedelta = DEFAULT_TIMEOUT

    @property
    def is_complete(self) -> bool:
        """Whether there is enough here to build a working adapter (D4).

        The switch *and* an address *and* a workspace. Two of the three is a
        half-configured deployment, and a half-configured deployment that tried
        to make requests would fail once per page view rather than once at boot.
        """
        return bool(self.enabled and self.base_url and self.default_workspace)

    @property
    def missing(self) -> tuple[str, ...]:
        """Which variables a deployment that meant to enable this still owes."""
        if not self.enabled:
            return (ENABLED,)
        declared = ((BASE_URL, self.base_url), (DEFAULT_WORKSPACE, self.default_workspace))
        return tuple(name for name, value in declared if not value)

    @property
    def api_root(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def web_root(self) -> str:
        """Where a person opens a document. Falls back to the API's own host."""
        return (self.web_url or self.base_url).rstrip("/")

    def address_of(self, workspace: str, document_id: str) -> str:
        """The address a stored reference carries, and the one a person clicks."""
        return self.web_root + DOCUMENT_PATH.format(workspace=workspace, document_id=document_id)


def settings_from(environment: Mapping[str, str] | None = None) -> ArcheSettings:
    """Read the five variables. Absent ones leave the defaults, which are off."""
    values = environment if environment is not None else os.environ
    return ArcheSettings(
        enabled=str(values.get(ENABLED, "")).strip().lower() in TRUE_VALUES,
        base_url=values.get(BASE_URL, "").strip(),
        default_workspace=values.get(DEFAULT_WORKSPACE, "").strip(),
        web_url=values.get(WEB_URL, "").strip(),
        timeout=_seconds(values.get(TIMEOUT, "")),
    )


def _seconds(declared: str) -> timedelta:
    """A budget in whole seconds, or the default when it is not a number.

    Tolerant on purpose: a typo in a *timeout* must not stop a deployment that
    is otherwise correctly configured, and the default is a safe answer.
    """
    try:
        value = float(declared)
    except ValueError:
        return DEFAULT_TIMEOUT
    return timedelta(seconds=value) if value > 0 else DEFAULT_TIMEOUT


__all__ = [
    "BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_WORKSPACE",
    "DOCUMENT_PATH",
    "ENABLED",
    "TIMEOUT",
    "VARIABLES",
    "WEB_URL",
    "ArcheSettings",
    "settings_from",
]
