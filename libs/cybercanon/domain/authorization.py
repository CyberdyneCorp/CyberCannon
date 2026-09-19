"""What a resolved actor may do — decided from the actor alone.

Two policies live here, and both are pure functions of value objects, which is
the requirement rather than a style preference: `agent-identity` demands that an
authorization decision be producible with no identity service reachable, so the
decision may not depend on anything but the :class:`~cybercanon.domain.identity.Actor`
already in hand. Nothing in this module knows what a token is.

The order the surfaces must follow is fixed by D3 — resolve the actor,
authorize, compile, then project the discipline lens — and it is an ordering
property precisely because a lens carries no authority: there is no parameter
here for one, so no code path can consult a lens for permission.

* :func:`may_read_project` answers *may this actor read this project*. An agent
  is permitted exactly what the actor it acts as is permitted, so there is no
  agent parameter: an escalation would need a signature that does not exist.
* :func:`may_author_durable_content` answers *may this caller write a constraint,
  a silhouette rule or any other durable specification content*. It refuses
  every automated caller regardless of the roles held, because an agent raising
  a budget so its own output passes is how trust in the system dies.
"""

from __future__ import annotations

from dataclasses import dataclass

from cybercanon.domain.identity import Actor, AgentId
from cybercanon.domain.tenancy import ProjectRef, project_ref

DURABLE_CONTENT = "durable specification content"
"""What agents may never author: constraints, silhouette rules, the spec itself."""

WRONG_TENANT = "belongs to another tenant"
"""Why a cross-organisation address is refused, in the words the refusal uses.

Deliberately the same sentence whether the project exists or not: a refusal that
distinguished them would answer "does this organisation have a project called
`x`" to anybody who asked.
"""


@dataclass(frozen=True)
class Decision:
    """Allowed, or refused with the sentence a surface prints.

    A bare boolean would force every caller to rebuild the reason, and the four
    surfaces would each phrase the refusal differently — which is how a person
    learns that the CLI and the agent disagree about what they may do.
    """

    allowed: bool
    reason: str = ""

    @property
    def refused(self) -> bool:
        return not self.allowed

    def __bool__(self) -> bool:
        return self.allowed


ALLOWED = Decision(allowed=True)
"""The unremarkable answer, shared because it carries no case-specific words."""


def may_read_project(actor: Actor, project: str | ProjectRef) -> Decision:
    """Whether this actor may read this project's specifications.

    Two rules, checked in this order:

    1. **tenancy** — when the project names a tenant, it must be the actor's.
       A project that names none asks no tenancy question, which is the case on
       an artist's laptop and the reason the command line never acquired one;
    2. **entitlement** — the project is among the ones the actor was resolved
       with. The local unauthenticated actor passes it because it is resolved
       with the project on this machine (D4), not because its kind is checked
       here — a kind that skipped the test would be a privilege only automated
       callers could reach, and there is no such thing.

    Tenancy comes first so that an address in another organisation is refused
    without the answer depending on whether a project of that name exists there.
    """
    subject = project_ref(project)
    if not actor.may_enter(subject):
        return Decision(
            allowed=False,
            reason=f"project {subject.name!r} {WRONG_TENANT}",
        )
    if actor.may_see(subject.name):
        return ALLOWED
    return Decision(
        allowed=False,
        reason=f"{actor.display} may not read project {subject.name!r}",
    )


def may_author_durable_content(actor: Actor, via: AgentId | None = None) -> Decision:
    """Whether this caller may create, modify or delete durable spec content.

    Two ways a caller is automated and both are refused: an agent acting as a
    person (`via`), and a service credential acting as nobody
    (:attr:`~cybercanon.domain.identity.Actor.is_automation`). The second
    arrived with the hosted surface, where background work authenticates with no
    person behind it; without it, "no agent may author durable content" would be
    enforced against the honest caller that declares its instrument and not
    against the one that has none.

    Neither branch consults the actor's roles, because the specification refuses
    an automated caller *regardless of the roles held by the actor it acts as*.
    A caller that read the roles would eventually find one worth making an
    exception for.
    """
    if actor.is_automation:
        return Decision(
            allowed=False,
            reason=(
                f"{actor.display} may not author {DURABLE_CONTENT}; "
                "background work reports, and a person decides"
            ),
        )
    if via is None:
        return ALLOWED
    return Decision(
        allowed=False,
        reason=(
            f"{via} may not author {DURABLE_CONTENT} on behalf of {actor.display}; "
            "an automated caller may report that a constraint is unattainable, "
            "and a person decides"
        ),
    )


__all__ = [
    "ALLOWED",
    "DURABLE_CONTENT",
    "WRONG_TENANT",
    "Decision",
    "may_author_durable_content",
    "may_read_project",
]
