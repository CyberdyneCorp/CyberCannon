"""Liveness, readiness and degradation — which dependency may withhold traffic.

`deployment-operations` splits one word people usually run together. *Live* is
whether the process is running, and answering it performs no input or output at
all. *Ready* is whether the service can serve its own requests. *Degraded* is
everything else being reported without any of it stopping a deploy.

The whole design is in one sentence of the specification: *"A service's
readiness SHALL depend only on the dependencies that service owns."* The
expensive failure it prevents is a cascade — a readiness check that touches the
model gateway, the identity provider or a sibling backend turns somebody else's
outage into a failed deploy of CyberCanon.

That leaves the interesting question: which dependencies does the API *own*?
The specification answers it component by component, and the answers are not
symmetrical:

* **the working copy** is owned, and a service that cannot reach it cannot serve
  a read at all — *"readiness SHALL report not ready, naming the working copy"*;
* **the index and the blob mirror** are owned but **rebuildable**. Git is the
  source of truth, so losing either degrades search and previews and loses
  nothing — *"a lost index does NOT withhold traffic"*, and *"answers derivable
  from the working copy alone SHALL continue to be served"*;
* **the model gateway, the identity provider and the document platform** are
  somebody else's, and are reported, never gated.

So :class:`Reliance` has three members rather than the two an "owned or
optional" split suggests, and the middle one is the whole point: *owned* and
*gating* are different questions, and conflating them is exactly how the index
ends up in a readiness check. Only :attr:`Reliance.OWNED` gates.

Nothing here observes anything. The composition root probes what it wired and
hands the observations in; this module classifies them. That keeps the rule
testable with no process, no socket and no container — and keeps an inbound
adapter from reaching an outbound one to answer a health check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

LANGUAGE_MODEL = "language_model"
DOCUMENT_PLATFORM = "document_platform"
IDENTITY_SERVICE = "identity_service"
SEARCH_INDEX = "search_index"
OBJECT_STORE = "object_store"
WORKING_COPY = "working_copy"
"""The names a dependency is described under, so two deployments agree on them.

Constants rather than free strings because the description is read by an
operator, by the status surface and by the readiness signal, and a name that
drifted between two releases would silently stop matching whatever reads it.
"""


class Reliance(Enum):
    """What this service loses when a dependency is gone.

    `OWNED` is the only one that withholds traffic. `REBUILDABLE` is owned state
    that git can reproduce, and `OPTIONAL` is another team's service; both
    degrade a feature and neither may fail a deploy.
    """

    OWNED = "owned"
    REBUILDABLE = "rebuildable"
    OPTIONAL = "optional"

    @property
    def gates(self) -> bool:
        """Whether readiness is allowed to be withheld because of this."""
        return self is Reliance.OWNED

    def __str__(self) -> str:
        return self.value


RELIANCE: Mapping[str, Reliance] = MappingProxyType(
    {
        WORKING_COPY: Reliance.OWNED,
        SEARCH_INDEX: Reliance.REBUILDABLE,
        OBJECT_STORE: Reliance.REBUILDABLE,
        IDENTITY_SERVICE: Reliance.OPTIONAL,
        LANGUAGE_MODEL: Reliance.OPTIONAL,
        DOCUMENT_PLATFORM: Reliance.OPTIONAL,
    }
)
"""The classification, entire, as one literal.

One table rather than a rule per component, so "what would stop a deploy" is
answerable by reading six lines — and so that adding a dependency without
deciding this is impossible rather than merely discouraged.
"""

AVAILABLE = "available"
UNAVAILABLE = "unavailable"


def reliance_of(name: str) -> Reliance:
    """How this service relies on that component. Unknown names never gate.

    A component nobody classified is treated as optional on purpose: the failure
    mode of guessing the other way is a deploy blocked by something nobody
    decided was essential, which is the cascade this module exists to prevent.
    """
    return RELIANCE.get(name, Reliance.OPTIONAL)


@dataclass(frozen=True)
class ComponentStatus:
    """One thing the process observed, and what it observed.

    Descriptive first: `available` and `detail` are what the composition root
    saw. `reliance` is what the specification says that means, defaulted from
    :data:`RELIANCE` so a caller cannot classify the index as gating by
    accident.
    """

    name: str
    available: bool = True
    detail: str = ""
    reliance: Reliance | None = None

    @property
    def relied_on(self) -> Reliance:
        return self.reliance if self.reliance is not None else reliance_of(self.name)

    @property
    def state(self) -> str:
        return AVAILABLE if self.available else UNAVAILABLE

    @property
    def withholds(self) -> bool:
        """Whether this observation is a reason to keep traffic away."""
        return not self.available and self.relied_on.gates

    @property
    def degrades(self) -> bool:
        """Whether this observation is a feature lost rather than a service down."""
        return not self.available and not self.relied_on.gates


@dataclass(frozen=True)
class ServiceHealth:
    """What the process can see, and the two signals that follow from it."""

    components: tuple[ComponentStatus, ...] = ()

    @property
    def live(self) -> bool:
        """Always true where this value exists: the process answered.

        Liveness is a property of the process, not of its dependencies, and the
        endpoint that reports it never builds one of these — it is here so that
        the two signals are visibly different things rather than one thing read
        twice.
        """
        return True

    @property
    def ready(self) -> bool:
        return not self.withholding

    @property
    def withholding(self) -> tuple[str, ...]:
        """The owned components that are down, named. Empty means ready."""
        return tuple(one.name for one in self.components if one.withholds)

    @property
    def degraded(self) -> tuple[str, ...]:
        """The components whose absence costs a feature and not the service."""
        return tuple(one.name for one in self.components if one.degrades)

    def named(self, name: str) -> ComponentStatus | None:
        for one in self.components:
            if one.name == name:
                return one
        return None


def describe_service_health(components: Sequence[ComponentStatus]) -> ServiceHealth:
    """Classify what was observed. The whole of the readiness decision.

    A pure function over values: the unit suite drives every case — owned down,
    optional down, rebuildable down, all up — with nothing running.
    """
    return ServiceHealth(tuple(components))


def unavailable(name: str, detail: str = "") -> ComponentStatus:
    """The observation a composition root records for something it cannot reach."""
    return ComponentStatus(name=name, available=False, detail=detail)


def available(name: str, detail: str = "") -> ComponentStatus:
    """The observation for something it can."""
    return ComponentStatus(name=name, available=True, detail=detail)


__all__ = [
    "AVAILABLE",
    "DOCUMENT_PLATFORM",
    "IDENTITY_SERVICE",
    "LANGUAGE_MODEL",
    "OBJECT_STORE",
    "RELIANCE",
    "SEARCH_INDEX",
    "UNAVAILABLE",
    "WORKING_COPY",
    "ComponentStatus",
    "Reliance",
    "ServiceHealth",
    "available",
    "describe_service_health",
    "reliance_of",
    "unavailable",
]
