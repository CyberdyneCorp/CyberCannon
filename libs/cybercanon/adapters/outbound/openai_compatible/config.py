"""What this deployment was told about a model, and nothing it can do without.

Seven variables, and the shape of the set is `project.md`'s standing rule:
**the master switch defaults to off and the system is fully usable with it off.**
A deployment that sets none of these behaves exactly as it did before this change
existed, which is what makes the whole feature removable rather than merely
optional.

The same five properties the document-platform settings have, for the same
reasons:

* **Environment only, no file fallback.** Coolify supplies configuration as
  environment, and a file that disagrees with it is a deployment behaving
  differently from how it is described.
* **Incomplete is off, not broken.** The switch on with no endpoint, or an
  endpoint with no model identifier, selects the null adapter. Half a
  configuration that made requests would fail once per click instead of behaving
  like the absence it is.
* **Model identifiers are opaque.** :attr:`ModelSettings.model` and
  :attr:`ModelSettings.vision_model` are passed to the endpoint verbatim. There
  is no allow-list here and no branch anywhere on their value — a new model is a
  configuration change, never a deploy.
* **Vision is separately configured**, so *text available, vision unavailable*
  is a state this type can hold rather than a special case inside one method.
* **The credential is never printed.** :class:`~cybercanon.adapters.wiring.configuration.Secret`
  is the service's version of this; here the value is held as a plain string
  inside a dataclass whose `repr` omits it, because a credential in a traceback
  is a credential in a log.

`canon` reads these from its own environment exactly as it reads the
CyberArche ones: the command line has no `ServiceConfiguration`, and a
composition root that could only be configured one way would make the feature
hosted-only for no reason anybody asked for.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta

ENABLED = "CANON_LLM_ENABLED"
BASE_URL = "CANON_LLM_BASE_URL"
API_KEY = "CANON_LLM_API_KEY"
MODEL = "CANON_LLM_MODEL"
VISION_MODEL = "CANON_LLM_VISION_MODEL"
TIMEOUT = "CANON_LLM_TIMEOUT_S"
MAX_RETRIES = "CANON_LLM_MAX_RETRIES"

VARIABLES: tuple[str, ...] = (
    ENABLED,
    BASE_URL,
    API_KEY,
    MODEL,
    VISION_MODEL,
    TIMEOUT,
    MAX_RETRIES,
)
"""Every variable this adapter reads, so a deployment document can be checked.

`tests/unit/test_model_settings.py` asserts this tuple is exactly the set the
service configuration declares, which is how the two readers of one environment
are kept from drifting apart.
"""

DEFAULT_TIMEOUT = timedelta(seconds=30)
"""How long one request may take before it is *not this time*.

Thirty seconds rather than five: a vision model describing a 4K concept sheet on
a busy on-prem gateway is not a page load, and a budget that expired before a
correct answer could arrive would make the feature look broken when it was
working.
"""

DEFAULT_MAX_RETRIES = 2
"""How many times a transient failure is tried again. Three attempts in all."""

TRUE_VALUES = ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ModelSettings:
    """The endpoint, the credential, two model identifiers and a failure budget."""

    enabled: bool = False
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    model: str = ""
    vision_model: str = ""
    timeout: timedelta = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES

    @property
    def is_complete(self) -> bool:
        """Whether a text completion can be attempted at all.

        The switch *and* an address *and* a model identifier. The credential is
        deliberately not required: a gateway on a private network that accepts
        unauthenticated calls is a real deployment, and demanding a key it does
        not want would make the on-prem case harder than the commercial one.
        """
        return bool(self.enabled and self.base_url and self.model)

    @property
    def vision_is_complete(self) -> bool:
        """Whether an image can be described — the same, plus a vision model."""
        return bool(self.is_complete and self.vision_model)

    @property
    def missing(self) -> tuple[str, ...]:
        """Which variables a deployment that meant to enable this still owes."""
        if not self.enabled:
            return (ENABLED,)
        declared = ((BASE_URL, self.base_url), (MODEL, self.model))
        return tuple(name for name, value in declared if not value)

    @property
    def absence(self) -> str:
        """Why generation is unavailable, in the words an operator can act on."""
        if not self.enabled:
            return f"{ENABLED} is off"
        owed = self.missing
        return f"{' and '.join(owed)} " + ("is" if len(owed) == 1 else "are") + " not set"

    @property
    def vision_absence(self) -> str:
        """The same, for image description, which needs one more identifier."""
        return self.absence if not self.is_complete else f"{VISION_MODEL} is not set"

    @property
    def api_root(self) -> str:
        """The endpoint with no trailing slash, so one join produces one path."""
        return self.base_url.rstrip("/")


def settings_from(environment: Mapping[str, str] | None = None) -> ModelSettings:
    """Read the seven variables. Absent ones leave the defaults, which are off."""
    values = environment if environment is not None else os.environ
    return ModelSettings(
        enabled=str(values.get(ENABLED, "")).strip().lower() in TRUE_VALUES,
        base_url=values.get(BASE_URL, "").strip(),
        api_key=values.get(API_KEY, "").strip(),
        model=values.get(MODEL, "").strip(),
        vision_model=values.get(VISION_MODEL, "").strip(),
        timeout=_seconds(values.get(TIMEOUT, "")),
        max_retries=_attempts(values.get(MAX_RETRIES, "")),
    )


def _seconds(declared: str) -> timedelta:
    """A budget in seconds, or the default when it is not a positive number.

    Tolerant on purpose, exactly as the document platform's is: a typo in a
    *timeout* must not stop a deployment that is otherwise correctly configured,
    and the default is a safe answer.
    """
    try:
        value = float(declared)
    except ValueError:
        return DEFAULT_TIMEOUT
    return timedelta(seconds=value) if value > 0 else DEFAULT_TIMEOUT


def _attempts(declared: str) -> int:
    """A retry budget, or the default. Never negative — zero means try once."""
    try:
        value = int(declared)
    except ValueError:
        return DEFAULT_MAX_RETRIES
    return max(value, 0)


__all__ = [
    "API_KEY",
    "BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "ENABLED",
    "MAX_RETRIES",
    "MODEL",
    "TIMEOUT",
    "VARIABLES",
    "VISION_MODEL",
    "ModelSettings",
    "settings_from",
]
