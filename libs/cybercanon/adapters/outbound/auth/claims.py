"""Verified claims in, a domain :class:`Actor` out. The whole of the translation.

This module is the boundary `auth-integration` draws and D12 restates: *"the
adapter verifies ... then maps configured groups to `Role`s and the subject to an
`ActorId`, producing an `Actor` with a `Tenant`"*. Everything the identity
service's data model calls things stops here — claim names, group names, the
shape of a token — and what continues is an actor the domain already knows how
to reason about.

Three rules this module exists to keep, each of which is a scenario:

* **A group with no configured mapping grants nothing**, and a credential whose
  groups are *all* unmapped resolves to an actor with no roles rather than a
  refusal. Refusing would make a mapping mistake look like an outage; resolving
  role-less makes it look like what it is, and the operation that needed a role
  refuses by naming the role.
* **No group is named in code.** :func:`roles_from` reads a mapping supplied by
  configuration and has no opinion about its contents, so *"adding a mapping
  requires no code change"* is structural rather than a promise.
* **The adapter never grants or denies.** Nothing here returns a decision, an
  allow, a deny or a permission. It returns an identifier and roles, and
  :func:`~cybercanon.domain.policy.decide` does the rest.

:class:`ClaimNames` holds *which claim* each thing is read from. Those are
defaults rather than configuration because they are the shape of the credential
this adapter is written against; what a studio changes is the group mapping,
which is where mistakes actually live.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cybercanon.domain.identity import Actor, ActorId, Role, automation_actor
from cybercanon.domain.tenancy import Tenant

CLIENT_CREDENTIALS = "client-credentials"
"""The grant a credential obtained with no person in the loop declares.

CyberdyneAuth follows the common convention of stating the grant type as a
claim, which is what lets background work be recognised *from the credential*
rather than from a naming convention on the subject — a convention an adapter
can forget to apply, which is the reason
:class:`~cybercanon.domain.identity.ActorKind` exists at all.
"""


@dataclass(frozen=True)
class ClaimNames:
    """Which claim carries which fact. The credential's shape, not a policy."""

    subject: str = "sub"
    display_name: str = "name"
    groups: str = "groups"
    projects: str = "projects"
    tenant: str = "tenant"
    git_emails: str = "git_emails"
    grant: str = "gty"


DEFAULT_CLAIMS = ClaimNames()


class ClaimsIncomplete(ValueError):
    """A verified credential carried no subject — there is nobody to act as."""


def roles_from(groups: Iterable[str], mapping: Mapping[str, str]) -> tuple[Role, ...]:
    """The domain roles these groups map to, in the role set's declared order.

    A group with no entry contributes nothing, and an entry naming something
    that is not a role contributes nothing either: a typo in configuration
    grants *less*, never more, which is the only direction a configuration
    mistake is allowed to fail in.

    The result is deduplicated and ordered by :class:`Role` rather than by the
    order the groups arrived in, so two credentials carrying the same groups in
    a different order resolve to actors that compare equal.
    """
    held = {
        role
        for group in groups
        if group in mapping
        if (role := Role.from_value(mapping[group])) is not None
    }
    return tuple(role for role in Role if role in held)


def actor_from(
    claims: Mapping[str, Any],
    *,
    group_roles: Mapping[str, str],
    names: ClaimNames = DEFAULT_CLAIMS,
) -> Actor:
    """The actor a verified credential resolves to — identifier and roles only.

    A credential declaring the client-credentials grant produces the automation
    actor, carrying the roles its groups map to. That is deliberate and it is
    the sharper half of the specified behaviour: automation holding *every* role
    is still refused every human-only operation, and the refusal lives in the
    domain registry rather than in a constructor that declined to give it any.
    """
    subject = _text(claims.get(names.subject))
    if not subject:
        raise ClaimsIncomplete(f"the credential carries no {names.subject!r} claim")
    roles = roles_from(_strings(claims.get(names.groups)), group_roles)
    projects = _strings(claims.get(names.projects))
    tenant = _tenant(claims.get(names.tenant))
    if _text(claims.get(names.grant)) == CLIENT_CREDENTIALS:
        return automation_actor(projects=projects, roles=roles, tenant=tenant, identifier=subject)
    return Actor(
        id=ActorId(subject),
        display_name=_text(claims.get(names.display_name)) or subject,
        roles=roles,
        projects=projects,
        tenant=tenant,
    )


def git_emails_from(
    claims: Mapping[str, Any], names: ClaimNames = DEFAULT_CLAIMS
) -> tuple[str, ...]:
    """The commit addresses the provider describes, or none at all (D13).

    None is the ordinary case and is an empty tuple rather than a failure:
    `.canon/actors.yaml` answers next, and the port is explicit that both shapes
    conform.
    """
    return _strings(claims.get(names.git_emails))


def _tenant(value: Any) -> Tenant | None:
    """The organisation the credential places this actor in, when it names one."""
    text = _text(value)
    return Tenant(text) if text else None


def _strings(value: Any) -> tuple[str, ...]:
    """A claim that may be a list, a space-separated string, or absent.

    Both spellings are in the wild — `groups` as an array, `scope` as a
    space-separated string — and accepting either here keeps the alternative out
    of every call site. Anything that is neither is no groups at all, because a
    claim this cannot read must not be read as a grant.
    """
    if isinstance(value, str):
        return tuple(item for item in value.split() if item)
    if isinstance(value, Sequence):
        return tuple(_text(item) for item in value if _text(item))
    return ()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "CLIENT_CREDENTIALS",
    "DEFAULT_CLAIMS",
    "ClaimNames",
    "ClaimsIncomplete",
    "actor_from",
    "git_emails_from",
    "roles_from",
]
