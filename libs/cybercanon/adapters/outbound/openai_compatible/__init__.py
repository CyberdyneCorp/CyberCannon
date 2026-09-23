"""The OpenAI-compatible model adapter — one wire format, chosen by environment.

`llm-integration` fixes the whole of this package's remit: *"The system SHALL
communicate with language and vision models exclusively through the
OpenAI-compatible Chat Completions interface"*, so that a commercial service, a
self-hosted gateway or a local proxy serve it without a code change.

Three modules, split so that everything which **decides** anything runs with no
socket anywhere:

* :mod:`~cybercanon.adapters.outbound.openai_compatible.config` — the seven
  environment variables, and the rule that absent or incomplete configuration is
  not an error but the absence of the feature;
* :mod:`~cybercanon.adapters.outbound.openai_compatible.transport` — building
  the documented request body and sending it, plus the mapping from every way of
  not answering onto exactly one reason;
* :mod:`~cybercanon.adapters.outbound.openai_compatible.models` — the adapter
  itself, implementing both ports over that transport.

The prompts are **not** here, and that is deliberate: D2 makes the instruction a
parameter of the port, so the layer that passes it is the application, and task
2.6 forbids the application from importing this package at all. They live in
:mod:`cybercanon.application.use_cases.prompts` — one per task, a constant in
code, with no tuning surface, which is what D10 is actually asking for.

**No provider SDK** (D1). The request is a dozen lines of JSON, and a vendor SDK
would bring base-URL quirks, auth assumptions, retry behaviour and version churn
in exchange for convenience — quietly making the on-prem gateway a second-class
target, which is exactly the coupling the requirement removes.
"""

from __future__ import annotations

from cybercanon.adapters.outbound.openai_compatible.config import (
    ModelSettings,
    settings_from,
)
from cybercanon.adapters.outbound.openai_compatible.models import OpenAICompatibleModels
from cybercanon.adapters.outbound.openai_compatible.transport import ChatTransport

__all__ = [
    "ChatTransport",
    "ModelSettings",
    "OpenAICompatibleModels",
    "settings_from",
]
