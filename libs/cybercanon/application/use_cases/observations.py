"""Recording an observation, and reporting a verdict somebody already has.

Two use cases, one for each of the two write tools `mcp-write-surface` permits,
and the number is *"a specified maximum, not a starting point"*. Everything an
automated caller may change lives here, which is the point: a third write is a
new function in this module, and a function in this module has to explain itself
against a specification that says there are two.

**`record_observation`** is eight steps and their order is load-bearing (D1, D4,
D9, D10):

1. resolve who is acting — with no arguments, so no caller can influence it;
2. require an identity, refusing with the sign-in action when there is none and
   as *unverifiable* when the credential can no longer be checked;
3. require the configured agent identifier, refusing rather than inventing one;
4. authorize — the ordinary matrix, plus the prohibition that an automated
   caller only observes;
5. **check the asset exists**, refusing an unknown identifier with the closest
   ones and writing nothing;
6. apply the rate limit, which is why step 5 comes first — a typo must not
   consume an artist's allowance;
7. suppress a near-duplicate, answering with the existing thread;
8. append, attributed to the person *and* the agent.

**`report_validation_outcome`** delivers a verdict that was produced elsewhere.
It evaluates nothing — this module imports no rule, no registry and no mesh
inspector, so *"no validation rule SHALL be evaluated as part of the report"* is
a property of the import list rather than a claim about a function body — and it
never fails for a delivery problem, because a report that can fail is a report
that eventually blocks a commit.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from cybercanon.application.errors import FailureKind, OperationFailed
from cybercanon.application.ports.annotation_writer import AnnotationWriter, WrittenAnnotation
from cybercanon.application.ports.clock import Clock, system_clock
from cybercanon.application.ports.credential_store import CredentialStore
from cybercanon.application.ports.outcome_reporter import (
    Delivery,
    OutcomeReporter,
    ReportedOutcome,
)
from cybercanon.application.ports.search_index import SearchIndex
from cybercanon.application.results import as_result, succeeded
from cybercanon.application.use_cases.lookup_assets import nearest_ids
from cybercanon.application.use_cases.resolve_actor import UNVERIFIABLE, Resolution, Resolver
from cybercanon.domain.annotations import Annotation, AnnotationKind, ObservationKind
from cybercanon.domain.identity import Actor, ActorKind, AgentId, Attribution, write_attribution
from cybercanon.domain.observations import (
    Allowance,
    ObservationRefused,
    WriteLimits,
    annotation_kind_of,
    duplicate_of,
    may_only_observe,
    observation,
    observation_kind_of,
    target_for,
    write_allowance,
)
from cybercanon.domain.policy import Operation, Subject, decide
from cybercanon.domain.report import Report
from cybercanon.domain.validation_outcome import verdict_hash

SIGN_IN_ACTION = "canon auth login"
"""The action a refusal names when no identity is available (D5).

A device-code flow needs a human at a browser, so a tool cannot start one: *"a
tool that blocks for two minutes waiting for a person to click is worse than a
refusal naming `canon login`."* The name is defined once, here, because a
refusal that named the wrong command would be worse than one that named none.
"""

NO_AGENT_IDENTIFIER = (
    "the server was started without an agent identifier, so a write could not "
    "name the agent that performed it; start it with `--agent <name>` (reads "
    "are unaffected)"
)
"""What a write is refused with when the launch configuration named no agent (D4).

Not a default, and that is the decision: *"defaulting a missing agent identifier
to `unknown-agent` ... is exactly the anonymous record the spec forbids, wearing
a name."*
"""

OBSERVATION_PREFIX = "obs"
"""What an observation's identifier begins with, so a reader can see its origin."""


# --------------------------------------------------------------------------
# Failures — each one means something different to the caller
# --------------------------------------------------------------------------


class WriteNeedsIdentity(OperationFailed):
    """No identity is available, so nothing may be written. Reads are untouched."""

    kind = FailureKind.UNAUTHENTICATED
    identifier = "write.needs_identity"

    def __init__(self, reason: str, subject: str = "this machine") -> None:
        super().__init__(f"{reason}; sign in with `{SIGN_IN_ACTION}`", subject)
        self.reason = reason


class WriteNeedsAgent(OperationFailed):
    """The process could not name the agent performing the write, so it is refused."""

    kind = FailureKind.UNAUTHENTICATED
    identifier = "write.needs_agent"

    def __init__(self, subject: str = "this server") -> None:
        super().__init__(NO_AGENT_IDENTIFIER, subject)


class WriteRefused(OperationFailed):
    """The policy refuses this write, carrying the kind the decision gave it."""

    identifier = "write.refused"

    def __init__(self, subject: str, reason: str, kind: FailureKind) -> None:
        super().__init__(reason, subject)
        self.kind = kind  # type: ignore[misc]


class UnknownWriteTarget(OperationFailed):
    """No asset with that identifier exists here, and nothing was created.

    The closest existing identifiers travel with the failure because the
    requirement asks for them in as many words — *"the response SHALL offer the
    closest existing identifiers"* — and a caller that was told only "no" has to
    guess which of its own strings was wrong.
    """

    kind = FailureKind.NOT_FOUND
    identifier = "write.unknown_asset"

    def __init__(self, asset_id: str, project: str, closest: Sequence[str] = ()) -> None:
        offer = f"; the closest are {', '.join(closest)}" if closest else ""
        super().__init__(
            f"no asset {asset_id!r} exists in project {project!r}{offer}. Nothing was "
            "written and no specification file was created",
            asset_id,
        )
        self.closest = tuple(closest)


class WriteThrottled(OperationFailed):
    """The caller has written too much, too fast, on this asset (D9)."""

    kind = FailureKind.CONFLICT
    identifier = "write.throttled"

    def __init__(self, asset_id: str, allowance: Allowance) -> None:
        super().__init__(allowance.reason, asset_id)
        self.allowance = allowance
        self.resets_at = allowance.resets_at


# --------------------------------------------------------------------------
# What a caller submits, and what comes back
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservationRequest:
    """One observation as the tool's arguments described it — four fields, no more.

    There is deliberately no author, actor, agent or state here. `add_annotation`
    takes *"asset, target, text, kind"*, identity comes from the credential and
    the agent from the launch configuration, and a shape with no slot for a
    claimed author cannot be handed one (`mcp-write-surface`: *"the supplied
    value SHALL have no effect on attribution"*).
    """

    asset: str
    target: str
    text: str
    kind: str
    observation_kind: str = ObservationKind.UNATTAINABLE_CONSTRAINT.value

    def parsed_kinds(self) -> tuple[AnnotationKind, ObservationKind]:
        """Both declared kinds, or the refusal naming the permitted values."""
        return annotation_kind_of(self.kind), observation_kind_of(self.observation_kind)


@dataclass(frozen=True)
class RecordedObservation:
    """What the write produced: the annotation, where it landed, and its standing.

    `suppressed` is true when this repeats an open observation the same agent
    already made (D10). The call still succeeds and still identifies a thread —
    *"It SHALL report the existing observation instead"* — because a refusal
    would teach a looping agent to rephrase, which is the noise the rule exists
    to prevent.
    """

    project: str
    asset_id: str
    path: str
    annotation: Annotation
    attribution: Attribution
    committed: bool = False
    suppressed: bool = False
    note: str = ""

    @property
    def id(self) -> str:
        return self.annotation.id

    @property
    def unanchored(self) -> bool:
        """Whether the target it named is not on the asset — preserved, not guessed."""
        return self.annotation.is_orphaned

    @property
    def attributed(self) -> str:
        """`rafa, via blender-agent` — what a human rendering of this record says."""
        return self.annotation.attribution


type Subjects = Callable[[str], Sequence[str] | None]
"""What an asset holds that an observation could anchor to, by asset identifier.

Injected rather than made a port method for the reason
:data:`~cybercanon.application.use_cases.resolve_actor.AuthorSource` is: the
answer comes from a mesh on one surface and from a concept block on another,
and ``None`` — *this caller does not know the set* — is a legitimate answer on
a machine with no export in hand.
"""


@dataclass
class WriteSession:
    """Everything a write needs, assembled by the composition root and by nothing else.

    `agent` is an :class:`~cybercanon.domain.identity.AgentId` or ``None``, and
    ``None`` is the server that was launched without one: it keeps every read
    and is refused both writes (D4). `resolver` takes no arguments, here as
    everywhere, so there is no signature through which a tool argument could
    reach the identity.
    """

    project: str
    resolver: Resolver
    writer: AnnotationWriter
    agent: AgentId | None = None
    search_index: SearchIndex | None = None
    subjects: Subjects | None = None
    clock: Clock = system_clock
    limits: WriteLimits = field(default_factory=WriteLimits)


# --------------------------------------------------------------------------
# Recording an observation
# --------------------------------------------------------------------------


@as_result
def record_observation(session: WriteSession, request: ObservationRequest) -> RecordedObservation:
    """Record one agent-authored observation against an asset that already exists.

    Everything this cannot do is what makes it safe, and each one is a signature
    rather than a promise: it takes no author, so attribution is the resolved
    person's; it takes no state, so the observation is created open and neither
    exit is reachable from here; and it has no parameter naming a constraint, a
    budget or a rule, so *"recording that a constraint is unattainable SHALL
    leave that constraint exactly as it was"* is true by the shape of the call.
    """
    kind, observed = _kinds(request)
    actor = _identified(session.resolver)
    agent = _agent(session.agent)
    _authorized(session, actor, agent)
    path = _existing(session, request.asset)
    recorded = session.writer.annotations(session.project, request.asset)
    _within_limits(session, actor, request.asset, recorded)
    candidate = _candidate(session, request, actor, agent, kind, observed)
    existing = duplicate_of(recorded, candidate)
    if existing is not None:
        return _suppressed(session, request, existing, actor, agent, path)
    written = session.writer.append(session.project, request.asset, candidate)
    return _recorded(session, request, written, actor, agent)


def _kinds(request: ObservationRequest) -> tuple[AnnotationKind, ObservationKind]:
    """Both declared kinds, with the domain's refusal in the outcome vocabulary.

    Parsed **first**, before identity is even resolved, because a value outside
    either closed set is a defect in the call rather than a question about who
    is asking — and because the refusal has to list the permitted values whether
    or not the caller happens to be signed in.
    """
    try:
        return request.parsed_kinds()
    except ObservationRefused as refusal:
        raise WriteRefused(refusal.subject, refusal.reason, FailureKind.INVALID) from refusal


@as_result
def writing_as(*, resolver: Resolver, agent: AgentId | None) -> Attribution:
    """The two-party attribution a write would carry, or why it can carry none (D4).

    Both write tools need the same gate — *"every write SHALL require a
    resolved, currently valid identity"*, and *"the agent's identifier SHALL
    come from the launch configuration"* — and they get it from one function so
    that the observation tool and the reporting tool cannot end up disagreeing
    about who may write. It refuses exactly where :func:`record_observation`
    refuses, in the same words, because it is the same two checks.

    It records nothing and reaches no port but the resolver: this answers *could
    a write be attributed*, never *write something*.
    """
    return write_attribution(_identified(resolver), _agent(agent))


def _identified(resolver: Resolver) -> Actor:
    """Who is writing, or the refusal that nobody verifiable is (D4, D5).

    Two refusals and they lead to different actions. *No credential* is answered
    with the sign-in action, because running it fixes the problem. *A credential
    that can no longer be verified* is answered as unverifiable, because signing
    in again is the fix and the distinction is what tells a person which of the
    two they are looking at. Reads pass through neither: this function is
    reachable only from a write.
    """
    resolution = resolver.resolve()
    if resolution.actor.kind is ActorKind.LOCAL:
        raise WriteNeedsIdentity(
            "writes name the person they are made on behalf of, and no credential "
            "is available on this machine"
        )
    if not resolution.verified:
        raise WriteNeedsIdentity(_unverifiable(resolution))
    if resolution.actor.is_automation:
        raise WriteNeedsIdentity(
            "this credential resolves to automation rather than to a person, and "
            "an observation names the person it was made on behalf of"
        )
    return resolution.actor


def _unverifiable(resolution: Resolution) -> str:
    detail = f" ({resolution.detail})" if resolution.detail else ""
    return (
        f"{resolution.actor.display}'s identity is {UNVERIFIABLE}{detail}, so a write "
        "could not be attributed to a verified person"
    )


def _agent(agent: AgentId | None) -> AgentId:
    """The configured agent identifier, or the refusal that there is none (D4)."""
    if agent is None:
        raise WriteNeedsAgent()
    return agent


def _authorized(session: WriteSession, actor: Actor, agent: AgentId) -> None:
    """Two questions, in the order that keeps both true.

    The prohibition first — an automated caller only observes, whatever roles it
    holds — and then the ordinary matrix, which decides whether this person may
    write in this project at all. Asking the matrix first would make the
    prohibition a second opinion; asking only the prohibition would let an agent
    write into a project its person cannot read.
    """
    subject = Subject(project=session.project, description=session.project)
    for decision in (
        may_only_observe(actor, Operation.CREATE_ANNOTATION, via=agent),
        decide(actor, Operation.CREATE_ANNOTATION, subject, via=agent),
    ):
        if decision.refused:
            raise WriteRefused(session.project, decision.reason, FailureKind.FORBIDDEN)


def _existing(session: WriteSession, asset_id: str) -> str:
    """Where this asset's specification is, or the refusal that it has none.

    Deliberately **before** the rate limit is consulted: a caller that misspelled
    an identifier has not written anything, and charging its allowance for a typo
    would throttle an agent for a mistake that left no trace.
    """
    path = session.writer.locate(session.project, asset_id)
    if path:
        return path
    raise UnknownWriteTarget(asset_id, session.project, _closest(session, asset_id))


def _closest(session: WriteSession, asset_id: str) -> tuple[str, ...]:
    """The nearest known identifiers, when this surface has an index to ask.

    The comparison is `asset-lookup`'s, not a second one invented here: *"a
    surface may not invent its own notion of close"*, so the command line and
    the agent suggest the same names for the same typo.
    """
    if session.search_index is None:
        return ()
    found = nearest_ids(asset_id, search_index=session.search_index, project=session.project)
    return found.value if succeeded(found) else ()


def _within_limits(
    session: WriteSession, actor: Actor, asset_id: str, recorded: Sequence[Annotation]
) -> None:
    """The durable half of D9's limit, computed from what the asset already holds."""
    allowance = write_allowance(
        actor=actor,
        asset_id=asset_id,
        recorded=recorded,
        now=session.clock(),
        limits=session.limits,
    )
    if allowance.refused:
        raise WriteThrottled(asset_id, allowance)


def _candidate(
    session: WriteSession,
    request: ObservationRequest,
    actor: Actor,
    agent: AgentId,
    kind: AnnotationKind,
    observed: ObservationKind,
) -> Annotation:
    """The observation as it would be recorded, before anything is written.

    Built through the domain's own constructor, so both attribution slots are
    filled or nothing is produced, and the anchor is the target *as given* —
    resolved when the asset has it, preserved and marked unanchored when it does
    not, and never quietly moved to a neighbouring part.
    """
    created_at = session.clock().replace(microsecond=0).isoformat()
    try:
        target = target_for(request.target, _subjects(session, request.asset))
        return observation(
            identifier=_identifier(request, created_at),
            author=actor.subject,
            via=agent,
            kind=kind,
            observation_kind=observed,
            text=request.text,
            target=target,
            created_at=created_at,
        )
    except ObservationRefused as refusal:
        raise WriteRefused(refusal.subject, refusal.reason, FailureKind.INVALID) from refusal


def _subjects(session: WriteSession, asset_id: str) -> Sequence[str] | None:
    """What this asset holds that an observation could anchor to, when known.

    ``None`` until a surface can answer it, which keeps the write from declaring
    every target dead on a machine with no export in hand. The unanchored case
    is still reachable the moment a surface does know the subjects.
    """
    return None if session.subjects is None else session.subjects(asset_id)


def _identifier(request: ObservationRequest, created_at: str) -> str:
    """A stable identifier derived from what the observation says and when.

    Content-derived for the same reason D7's outcome identity is: an agent that
    crashed and restarted has no client-generated identifier left, and the only
    value both sides agree on is the content. The creation time is part of it so
    that an observation raised again *after a person resolved it* is a new
    thread rather than a collision — which is precisely what D10 requires.
    """
    seed = "|".join(
        (
            request.asset,
            request.target,
            request.kind,
            request.observation_kind,
            request.text,
            created_at,
        )
    )
    return f"{OBSERVATION_PREFIX}_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _recorded(
    session: WriteSession,
    request: ObservationRequest,
    written: WrittenAnnotation,
    actor: Actor,
    agent: AgentId,
) -> RecordedObservation:
    """What the caller is told about a write that happened."""
    return RecordedObservation(
        project=session.project,
        asset_id=request.asset,
        path=written.path,
        annotation=written.annotation,
        attribution=write_attribution(actor, agent),
        committed=written.committed,
        note=written.note,
    )


def _suppressed(
    session: WriteSession,
    request: ObservationRequest,
    existing: Annotation,
    actor: Actor,
    agent: AgentId,
    path: str,
) -> RecordedObservation:
    """What the caller is told about a write that was already there (D10)."""
    return RecordedObservation(
        project=session.project,
        asset_id=request.asset,
        path=path,
        annotation=existing,
        attribution=write_attribution(actor, agent),
        suppressed=True,
        note=(
            f"observation {existing.id} already says this and is still open; nothing was written"
        ),
    )


# --------------------------------------------------------------------------
# Reporting an outcome somebody already has (D6, D7)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportedRun:
    """What reporting achieved — never a verdict, and never a reason to stop.

    `outcome` is the verdict as it was handed in, unchanged, which is the whole
    requirement: *"the reported outcome SHALL be identical to the verdict the
    same caller already received locally."*
    """

    outcome: ReportedOutcome
    delivery: Delivery

    @property
    def pending(self) -> int:
        return self.delivery.pending

    @property
    def delivered(self) -> bool:
        return self.delivery.complete

    @property
    def note(self) -> str:
        """What the caller is told: nothing when it landed, the standing verdict when not."""
        return "" if self.delivered else str(self.delivery)


@as_result
def report_validation_outcome(
    report: Report,
    *,
    reporter: OutcomeReporter,
    export: str,
    export_hash: str,
    attribution: Attribution | None = None,
    clock: Clock = system_clock,
) -> ReportedRun:
    """Deliver a verdict that already exists. Nothing here produces one.

    `report` is the domain's own :class:`~cybercanon.domain.report.Report`,
    handed in by whoever ran the validation, and it is copied rather than
    consulted: the counts and the digest are read off it and no rule, registry
    or mesh inspector is reachable from this module at all.

    It cannot fail for a delivery problem. `reporter.report` retains what it
    could not send and answers; this returns successfully either way, which is
    the only construction under which *"a failure to deliver ... SHALL NOT block
    a commit"* survives a pre-commit hook.
    """
    outcome = ReportedOutcome(
        asset_id=report.asset_id,
        export=export,
        export_hash=export_hash,
        verdict_hash=verdict_hash(report),
        passed=report.passed,
        errors=len(report.errors),
        warnings=len(report.warnings),
        reported_at=clock().replace(microsecond=0).isoformat(),
        attributed_to=str(attribution.actor) if attribution else "",
        via=str(attribution.via) if attribution and attribution.via else "",
    )
    return ReportedRun(outcome=outcome, delivery=reporter.report(outcome))


type ExportDigest = Callable[[str], str]
"""What an export's bytes hash to, by path — half of D7's identity.

Injected the way :data:`Subjects` and
:data:`~cybercanon.application.use_cases.index_assets.Fingerprinter` are, and
for the same reason: the digest comes off a file on a laptop and out of a git
object database on the hosted surface, and neither belongs in a use case that
must remain able to run with no file system at all.
"""


def no_export_digest(export: str) -> str:
    """The default: this caller cannot hash the export, and says so by answering nothing.

    An empty digest is honest rather than convenient. D7's triple still
    identifies the outcome by its asset and its verdict, and an invented digest
    would make a re-export look like a retry — the one confusion the triple
    exists to prevent.
    """
    return ""


@as_result
def flush_reports(*, reporter: OutcomeReporter) -> Delivery:
    """Attempt to deliver everything retained. Exits on what is left, never on a failure."""
    return reporter.flush()


# --------------------------------------------------------------------------
# Who this machine is signed in as (task 2.9)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Identity:
    """What `canon whoami` answers: the person, the agent, and what is waiting.

    `pending_reports` is here rather than in a second command because a silent
    reporting outage has to be visible *where a person already looks* — D6's own
    mitigation for *"reports silently stop arriving and nobody notices."*
    """

    actor: str
    display: str
    signed_in: bool
    verified: bool
    stored_in: str = ""
    agent: str = ""
    pending_reports: int = 0
    detail: str = ""

    @property
    def may_write(self) -> bool:
        """Whether a write would be accepted right now — identity and agent both."""
        return self.signed_in and self.verified and bool(self.agent)

    def __str__(self) -> str:
        who = f"{self.display}, via {self.agent}" if self.agent else self.display
        state = "signed in" if self.signed_in else "not signed in"
        return f"{who} — {state}, {self.pending_reports} report(s) pending"


@as_result
def show_identity(
    *,
    resolver: Resolver,
    credential_store: CredentialStore | None = None,
    reporter: OutcomeReporter | None = None,
    agent: AgentId | None = None,
) -> Identity:
    """Who this machine writes as, whether it can, and what has not been delivered.

    Every port is optional because this has to answer on a machine that has
    signed into nothing and reported nothing — which is the machine `canon
    validate` is built for, and the one where this question is most often asked.
    """
    resolution = resolver.resolve()
    held, unreachable = _credential_state(credential_store)
    return Identity(
        actor=resolution.actor.subject,
        display=resolution.actor.display,
        signed_in=held,
        verified=resolution.verified,
        stored_in=_where(credential_store),
        agent=str(agent) if agent else "",
        pending_reports=len(reporter.pending()) if reporter is not None else 0,
        detail="; ".join(part for part in (resolution.detail, unreachable) if part),
    )


def _credential_state(credential_store: CredentialStore | None) -> tuple[bool, str]:
    """Whether a credential is held here — never what it is — and why nobody could ask.

    A store that cannot be reached answers *no*, and now also answers *why*: D5
    requires that when the keychain is unavailable *"the system reports that
    writes are unavailable and keeps reads working, rather than falling back to
    a file"*, and a person told only "not signed in" would sign in again into
    the same locked store. The reason travels; the credential never does.
    """
    if credential_store is None:
        return False, ""
    try:
        return credential_store.load() is not None, ""
    except OperationFailed as unavailable:
        return False, unavailable.message


def _holds_credential(credential_store: CredentialStore | None) -> bool:
    """Whether a credential is stored here — never what it is."""
    return _credential_state(credential_store)[0]


def _where(credential_store: CredentialStore | None) -> str:
    """How the store names itself, as :func:`sign_in` names it — one phrasing."""
    if credential_store is None:
        return ""
    return str(getattr(credential_store, "description", "") or type(credential_store).__name__)


__all__ = [
    "NO_AGENT_IDENTIFIER",
    "OBSERVATION_PREFIX",
    "SIGN_IN_ACTION",
    "ExportDigest",
    "Identity",
    "ObservationRequest",
    "RecordedObservation",
    "ReportedRun",
    "Subjects",
    "UnknownWriteTarget",
    "WriteNeedsAgent",
    "WriteNeedsIdentity",
    "WriteRefused",
    "WriteSession",
    "WriteThrottled",
    "flush_reports",
    "no_export_digest",
    "record_observation",
    "report_validation_outcome",
    "show_identity",
    "writing_as",
]
