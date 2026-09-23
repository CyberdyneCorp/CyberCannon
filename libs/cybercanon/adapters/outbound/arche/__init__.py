"""CyberArche — the document platform CyberCanon links to.

One adapter, one port, no fan-out. Everything CyberArche's API calls things —
workspaces, blocks, snapshots, the bearer header, the status codes — is confined
to this package, and the composition root chooses between it and
:class:`~cybercanon.application.ports.document_platform.NullDocumentPlatform`
once, by configuration (D4).
"""

from cybercanon.adapters.outbound.arche.config import (
    ArcheSettings,
    settings_from,
)
from cybercanon.adapters.outbound.arche.platform import ArcheDocumentPlatform
from cybercanon.adapters.outbound.arche.transport import ArcheTransport, Response

__all__ = [
    "ArcheDocumentPlatform",
    "ArcheSettings",
    "ArcheTransport",
    "Response",
    "settings_from",
]
