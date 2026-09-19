"""Tenancy: which organisation a project belongs to, and who may see it.

A hosted surface serves several organisations from one process, so "may this
actor read this project" acquires a second half: the project has to belong to
the tenant the actor was resolved with. `auth-integration` fixes where that
answer comes from — **verified claims and nothing else** — and fixes what must
never work: a tenant taken from a path segment, a query parameter or a request
body. The consequence for this module is that nothing here parses anything. A
:class:`Tenant` is a value the adapter hands in already verified, and the
decision over it is a pure function like every other decision in the domain.

`ProjectRef` exists because a bare project name cannot carry that second half.
The policy still accepts a plain string — the command line and the local MCP
server have one project and no tenant at all (D4) — and tenancy simply does not
apply there. A reference that *does* name a tenant is checked against the
actor's, which is what makes "a path-supplied tenant cannot widen access"
structural: widening would require the caller to change the actor, and the
actor comes from the credential.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    """The organisation a project and an actor belong to.

    A value object rather than a bare `str` for the reason
    :class:`~cybercanon.domain.identity.ActorId` is one: it is compared in an
    authorization decision, and a string there is confusable with a project
    name, a display name or a group.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError(f"tenant {self.value!r} must be non-empty and unpadded")
        if any(character.isspace() for character in self.value):
            raise ValueError(f"tenant {self.value!r} must not contain whitespace")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProjectRef:
    """A project, and the tenant it belongs to when one is known.

    `tenant` is ``None`` for a project nobody has placed in an organisation —
    the working copy on an artist's laptop, which the local unauthenticated
    actor reads with no identity service in sight. A reference with no tenant
    asks no tenancy question; it does not answer it permissively.
    """

    name: str
    tenant: Tenant | None = None

    def __post_init__(self) -> None:
        if self.name.strip() != self.name:
            raise ValueError(f"project {self.name!r} must be unpadded")

    def __str__(self) -> str:
        return self.name


def project_ref(project: str | ProjectRef) -> ProjectRef:
    """A reference, whatever the caller had: a bare name carries no tenant.

    The one conversion, so that every policy function takes both shapes and
    none of them re-derives the rule that a bare name is tenant-free.
    """
    return project if isinstance(project, ProjectRef) else ProjectRef(name=project)


def tenants_agree(actor_tenant: Tenant | None, subject: ProjectRef) -> bool:
    """Whether this actor's tenant admits this project.

    Three cases, and only one of them is a refusal:

    * the project names no tenant — tenancy does not apply, and the projects
      the actor was resolved with decide alone;
    * the project names the actor's tenant — it applies and it agrees;
    * the project names another tenant, or the actor has none — refused.

    An actor with no tenant is refused a tenanted project deliberately: the
    alternative reads "no tenant means every tenant", which is the shape of
    every cross-organisation leak.
    """
    if subject.tenant is None:
        return True
    return actor_tenant == subject.tenant


__all__ = ["ProjectRef", "Tenant", "project_ref", "tenants_agree"]
