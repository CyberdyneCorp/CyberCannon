"""The actor mapping: one person, two identities, resolved in both directions.

Because git is the source of truth, every person has an authenticated subject
*and* a git commit author email. Unlinked, the Rafa who annotated in the web app
and the `rafa@cyberdyne.com` who committed `asset.yaml` are two people in the
history and attribution breaks silently. `.canon/actors.yaml` binds them, and
this module is what the file *means*: :class:`ActorBinding` values held by an
:class:`ActorMapping`, with resolution as pure functions over it (D12).

Reading the file is an adapter's job — it is repository content like
`asset.yaml`, fetched through `SpecStore` at the same revision as the specs it
explains — so nothing here parses YAML, touches disk or knows a path. The domain
takes already-parsed values, which is the same boundary that lets the validator
suite run over hand-built `MeshFacts` with no file on disk.

Three properties the specification fixes, and they are all here:

* **Both directions come from one mapping**, so the two answers cannot disagree.
* **Email comparison is case-insensitive**, because `RAFA@Cyberdyne.com` and
  `rafa@cyberdyne.com` are one person and a commit records whichever the
  author's client sent.
* **An unmatched email is a value, never a null and never a guess** (D14). It
  resolves to the unknown actor from
  :func:`~cybercanon.domain.identity.unmapped_actor`, carrying the email
  verbatim; the nearest similar entry is never substituted, because a wrong
  attribution is worse than an absent one.

`default_role` is kept as the *declared text* rather than a parsed
:class:`~cybercanon.domain.identity.Role`, for the reason
:mod:`cybercanon.domain.spec_checks` keeps a declared status as text: a role
outside the defined set is a reportable violation of the file, and a parse that
raised would deny the reader every other finding in the same run.
"""

from __future__ import annotations

from dataclasses import dataclass

from cybercanon.domain.identity import Actor, ActorId, Role, unmapped_actor

ACTORS_PATH = ".canon/actors.yaml"
"""Where the mapping is authored, relative to the repository root."""


def normalize_email(email: str) -> str:
    """The comparison form of a git author email: trimmed and lower-cased."""
    return email.strip().lower()


@dataclass(frozen=True)
class GitAuthor:
    """A git commit identity: the name and email a commit is authored with.

    Both halves are carried because both are needed. Resolving a commit needs
    only the email, but committing *on a person's behalf* needs the name too,
    and a value that held one of them would force the other to be re-derived at
    the call site — which is how the two directions start disagreeing.
    """

    name: str
    email: str

    @property
    def key(self) -> str:
        """The email in comparison form."""
        return normalize_email(self.email)

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


@dataclass(frozen=True)
class ActorBinding:
    """One entry of the mapping: a subject and the git identities it owns.

    `emails` is ordered and the order is meaningful: the first listed is the
    address used for changes committed on this person's behalf. A person who
    changes address *adds* an email rather than replacing one, so commits
    authored under the old address keep resolving.
    """

    subject: str
    display_name: str
    emails: tuple[str, ...] = ()
    chat_handle: str | None = None
    default_role: str | None = None

    @property
    def role(self) -> Role | None:
        """The declared default role, or ``None`` when it names no known role."""
        return Role.from_value(self.default_role) if self.default_role else None

    @property
    def keys(self) -> tuple[str, ...]:
        """Every declared email in comparison form."""
        return tuple(normalize_email(email) for email in self.emails)

    @property
    def primary_email(self) -> str | None:
        """The address commits on this person's behalf are authored with."""
        return self.emails[0] if self.emails else None

    def owns(self, email: str) -> bool:
        """Whether this entry claims that email — exact, case-insensitive, never fuzzy."""
        return normalize_email(email) in self.keys


@dataclass(frozen=True)
class ActorMapping:
    """Every binding a project declares. An absent file is an empty mapping."""

    bindings: tuple[ActorBinding, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.bindings


EMPTY_MAPPING = ActorMapping()
"""What a project without `.canon/actors.yaml` has. It stays fully readable."""


def binding_for_subject(mapping: ActorMapping, subject: str) -> ActorBinding | None:
    """The entry declaring this identity subject, if the mapping declares one."""
    return next((binding for binding in mapping.bindings if binding.subject == subject), None)


def binding_for_email(mapping: ActorMapping, email: str) -> ActorBinding | None:
    """The entry claiming this git author email, compared case-insensitively."""
    return next((binding for binding in mapping.bindings if binding.owns(email)), None)


def actor_for(binding: ActorBinding) -> Actor:
    """The actor an entry describes: its subject, its name and its default role.

    An entry whose declared role is outside the defined set yields an actor with
    no roles rather than a guess. The defect is reported by
    :mod:`cybercanon.domain.actor_checks`; resolution's job is to stay total.
    """
    role = binding.role
    return Actor(
        id=ActorId(binding.subject),
        display_name=binding.display_name,
        roles=(role,) if role else (),
    )


def resolve_git_author(mapping: ActorMapping, email: str) -> Actor:
    """The actor that committed under this email — always an actor (D14).

    An unmatched address resolves to the explicitly unknown actor carrying it
    verbatim. Nothing here approximates: `r.santos@cyberdyne.com` does not
    become the person holding `rafa@cyberdyne.com`, however similar they look.
    """
    binding = binding_for_email(mapping, email)
    return actor_for(binding) if binding else unmapped_actor(email)


def resolve_subject(mapping: ActorMapping, subject: str) -> Actor:
    """The actor this identity subject names — always an actor, never ``None``.

    A subject the mapping does not declare resolves to the unknown actor
    carrying the subject verbatim, for the same reason an unmatched email does:
    one forgiving ``or current_actor`` at a call site is all it takes to
    misattribute history to whoever happened to be asking.
    """
    binding = binding_for_subject(mapping, subject)
    return actor_for(binding) if binding else unmapped_actor(subject)


def git_author_for(mapping: ActorMapping, actor: Actor) -> GitAuthor | None:
    """The git identity to author a change with on this actor's behalf.

    ``None`` means *this person has no mapped git identity*, which the surface
    that commits refuses with a message naming the missing entry — the one
    place a missing binding must stop an operation rather than degrade it. It is
    not part of the resolution chain D14 governs: that chain answers *who is
    this*, always with an actor, and this function answers *may we sign as them*.

    An unknown actor answers with the address it was resolved from, so the round
    trip through :func:`resolve_git_author` is stable for mapped and unmapped
    people alike.
    """
    binding = binding_for_subject(mapping, actor.id.value)
    if binding and binding.primary_email:
        return GitAuthor(name=binding.display_name, email=binding.primary_email)
    if actor.is_unmapped and actor.unmapped_as:
        return GitAuthor(name=actor.display_name, email=actor.unmapped_as)
    return None


def unmapped_authors(mapping: ActorMapping, emails: tuple[str, ...]) -> tuple[Actor, ...]:
    """The distinct authors among `emails` that the mapping does not bind.

    Distinct by comparison form and ordered by first appearance, so a project's
    missing entries can be listed once each and worked through.
    """
    seen: set[str] = set()
    found: list[Actor] = []
    for email in emails:
        key = normalize_email(email)
        if key in seen or binding_for_email(mapping, email) is not None:
            continue
        seen.add(key)
        found.append(unmapped_actor(email))
    return tuple(found)


__all__ = [
    "ACTORS_PATH",
    "EMPTY_MAPPING",
    "ActorBinding",
    "ActorMapping",
    "GitAuthor",
    "actor_for",
    "binding_for_email",
    "binding_for_subject",
    "git_author_for",
    "normalize_email",
    "resolve_git_author",
    "resolve_subject",
    "unmapped_authors",
]
