"""One question, two answers, and never one list: local exact, delegated prose.

`semantic-search-delegation` splits search into two honest halves. Exact lookup
over identifiers, names, aliases, tags, status and owners stays here — local,
deterministic, no network, no embeddings. A natural-language question about
long-form prose is *additionally* forwarded to the document platform's own
retrieval, **with the asking person's own credential**, and what comes back is
presented beside the exact results rather than mixed into them.

Four decisions make that more than a description:

* **The routing gate is syntactic, not a classifier (D7).** Delegation happens
  when the local cascade produced nothing *and* the query looks like prose
  rather than an identifier. It is a pure function of the query and the local
  result set, so anybody can say why a query was or was not delegated —
  `project.md` forbids the lookup path depending on a reachable model, and an
  intent classifier would put one there.
* **The local half runs to completion before the remote half is asked (D5).**
  Not concurrently: *"local results SHALL be produced for every query
  regardless of whether delegation occurs or succeeds"* is then a property of
  the ordering rather than a question about scheduling. The accepted cost is
  worst-case latency of local time plus the budget.
* **Provenance is stamped by the producer and the two groups are never merged
  (D6).** :class:`ExactResult` carries `EXACT` and :class:`SemanticResult`
  carries `SEMANTIC`; neither carries a score, so *"no ordering value SHALL
  rank a semantic result against an exact one"* holds because the comparison is
  unwritable, not because nobody wrote it.
* **A semantic hit is a passage in a document, not an asset record.**
  :class:`SemanticResult` has no asset identifier and no location — it names
  the document it came from and where to open it, and nothing else. A passage
  mentioning `mech_scout` therefore *cannot* be rendered as that asset's
  specification; the asset's own record is reachable only through the exact
  results.

Every way the platform can fail to answer leaves the local results untouched and
names the reason (unconfigured, unreachable, rejected, timed out, malformed), so
a degraded answer says it is degraded instead of silently narrowing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from cybercanon.application.errors import OperationFailed
from cybercanon.application.ports.document_platform import (
    DEFAULT_BUDGET,
    NO_CREDENTIAL,
    Credential,
    DocumentPlatform,
    NullDocumentPlatform,
    Passage,
    PlatformUnavailable,
    UnavailabilityReason,
)
from cybercanon.application.ports.search_index import MatchKind, SearchHit, SearchIndex
from cybercanon.application.results import as_result
from cybercanon.application.use_cases.lookup_assets import SearchAnswer, search_assets
from cybercanon.domain.documents import (
    ProvenanceGroup,
    ResultProvenance,
    grouped_by_provenance,
)

# --------------------------------------------------------------------------
# What the two groups are called, and what the second one has to admit
# --------------------------------------------------------------------------

EXACT_LABEL = "exact matches"
SEMANTIC_LABEL = "approximate matches from linked documents"

GROUP_LABELS: Mapping[ResultProvenance, str] = {
    ResultProvenance.EXACT: EXACT_LABEL,
    ResultProvenance.SEMANTIC: SEMANTIC_LABEL,
}
"""The label each group is presented under. Exact first, always — the order is
:data:`~cybercanon.domain.documents.PROVENANCE_ORDER`'s and not this module's."""

APPROXIMATE_NOTICE = (
    "these passages were retrieved approximately from linked documents; they "
    "are not an asset's specification and they are not a definitive answer"
)
"""What the semantic group says about itself, every time it is shown.

The cheap version of the mistake this prevents — a retrieved passage quoted as
though it were a constraint — is the one the whole product exists to prevent.
"""


def label_for(provenance: ResultProvenance) -> str:
    """What this group of results is called on screen."""
    return GROUP_LABELS[provenance]


# --------------------------------------------------------------------------
# The routing gate (D7) — a pure function of the query and the local results
# --------------------------------------------------------------------------

IDENTIFIER_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
"""What an identifier looks like: one token of the alphabet asset ids are written in."""

MINIMUM_PROSE_WORDS = 3
"""How many words a query needs before it reads as a question rather than a name.

Two words is `scout mech`, which is a name somebody typed with a space in it.
Three is the point at which delegating costs less than the person rephrasing —
and the gate is a number here rather than a judgement precisely so that a query
that lands on the wrong side of it shows up in the local miss log (D7's accepted
cost) instead of in an argument about a classifier.
"""


def is_identifier_shaped(query: str) -> bool:
    """Whether this query is one token that could be an identifier or an alias."""
    return bool(IDENTIFIER_SHAPE.fullmatch(query.strip()))


def words_in(query: str) -> tuple[str, ...]:
    return tuple(word for word in query.strip().split() if word)


def is_prose(query: str) -> bool:
    """Whether this query reads as natural language rather than as a name.

    Three tests, all syntactic and all cheap: it has whitespace in it, it has
    at least :data:`MINIMUM_PROSE_WORDS` words, and it is not identifier-shaped.
    """
    words = words_in(query)
    return len(words) >= MINIMUM_PROSE_WORDS and not is_identifier_shaped(query)


RESOLVING_KINDS: tuple[MatchKind, ...] = (
    MatchKind.EXACT_ID,
    MatchKind.NAME_PREFIX,
    MatchKind.ALIAS,
    MatchKind.TAG,
)
"""The four passes that count as the query having *resolved to* something.

The requirement names them exactly — *"a query that does not resolve to an
exact identifier, name, alias or tag"* — and leaves the fifth pass out, which
is the difference between a gate that works and one that cannot satisfy its own
scenarios. A description substring is a weak match over prose somebody wrote
about the asset, and a sentence that only matched one is precisely the sentence
worth also asking the document platform about: *"a query producing both exact
and semantic results"* is a case the specification renders, so it has to be a
case the gate can produce.
"""


def resolved_locally(local: Sequence[SearchHit]) -> bool:
    """Whether the local cascade answered the question rather than brushed against it."""
    return any(hit.kind in RESOLVING_KINDS for hit in local)


def should_delegate(query: str, local: Sequence[SearchHit]) -> bool:
    """Whether this query is additionally forwarded to the retrieval service.

    Both halves of the requirement, and in this order: *"a query that does not
    resolve to an exact identifier, name, alias or tag, **and** that is shaped
    as natural language rather than an identifier"*. An identifier that matched
    is never delegated, and neither is one that did not — `mech_scoot` is a
    typo, and the answer to a typo is the near-miss list, not a retrieval.
    """
    return not resolved_locally(local) and is_prose(query)


# --------------------------------------------------------------------------
# The two kinds of result — each stamped by its producer (D6)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExactResult:
    """One local hit: the asset, and the pass of the cascade that found it.

    `matched` is inspectable ranking *within* this group and exists nowhere in
    the other one, which is the mechanical half of *"no ordering value SHALL
    rank a semantic result against an exact one"*.
    """

    asset_id: str
    name: str
    matched: MatchKind

    @property
    def provenance(self) -> ResultProvenance:
        return ResultProvenance.EXACT

    @classmethod
    def of(cls, hit: SearchHit) -> ExactResult:
        return cls(asset_id=hit.asset_id, name=hit.entry.name, matched=hit.kind)


@dataclass(frozen=True)
class SemanticResult:
    """One approximate passage: the text, and the document it came from.

    **No asset identifier, no location, no score.** A passage that mentions an
    asset by name is a sentence somebody wrote in a document, and the moment it
    carried an `asset` field a surface would render it as that asset's record —
    which is the confusion the requirement exists to prevent. There is likewise
    no rank and no relevance number: retrieval's own ordering stays inside the
    retrieval service, where `design.md`'s non-goals leave it.
    """

    workspace: str
    document_id: str
    document_title: str
    url: str
    text: str = ""

    @property
    def provenance(self) -> ResultProvenance:
        return ResultProvenance.SEMANTIC

    @property
    def source(self) -> str:
        """The document this passage came from, named — its title or its address."""
        return self.document_title or self.url

    @property
    def is_openable(self) -> bool:
        """Whether this passage can be opened where it lives."""
        return bool(self.url)

    @classmethod
    def of(cls, passage: Passage) -> SemanticResult:
        return cls(
            workspace=passage.workspace,
            document_id=passage.document_id,
            document_title=passage.title,
            url=passage.url,
            text=passage.text,
        )


# --------------------------------------------------------------------------
# Why the semantic half is not here, when it is not
# --------------------------------------------------------------------------

NO_AUTHORITY = (
    "no credential was presented with this query, so nothing was asked of the "
    "document platform on this person's behalf and only exact results are shown"
)
"""*"No forwardable credential means local only."*

The alternative — asking under the deployment's own credential — is the exact
thing the specification forbids, so the call is not made at all rather than made
as somebody else.
"""

UNAVAILABLE_SENTENCES: Mapping[UnavailabilityReason, str] = {
    UnavailabilityReason.UNCONFIGURED: (
        "this deployment has no document platform configured, so only exact results are shown"
    ),
    UnavailabilityReason.UNREACHABLE: (
        "the document platform could not be reached, so only exact results are shown"
    ),
    UnavailabilityReason.REJECTED: (
        "the document platform did not accept this caller's credential, so only "
        "exact results are shown"
    ),
    UnavailabilityReason.TIMED_OUT: (
        "the document platform did not answer within the time budget, so only "
        "exact results are shown"
    ),
    UnavailabilityReason.MALFORMED: (
        "the document platform answered in a shape this version does not "
        "understand, so only exact results are shown"
    ),
}
"""One sentence per reason, and five reasons. A surface renders the sentence; the
reason is what a caller distinguishes on, which is why both travel."""


@dataclass(frozen=True)
class SemanticGroup:
    """The approximate half of an answer, present whether or not it has results.

    Always present, empty or not: a response that dropped this group when the
    platform was down would be indistinguishable from one that never asked, and
    *"the response SHALL state that semantic results were unavailable and why"*
    needs somewhere to hang.
    """

    results: tuple[SemanticResult, ...] = ()
    delegated: bool = False
    reason: UnavailabilityReason | None = None
    detail: str = ""

    @property
    def is_available(self) -> bool:
        return self.reason is None

    @property
    def label(self) -> str:
        return SEMANTIC_LABEL

    @property
    def is_approximate(self) -> bool:
        """Always. It is what this group is, not something it sometimes becomes."""
        return True

    @property
    def notice(self) -> str:
        """What this group says about itself — why it is empty, or that it guesses."""
        return self.detail if self.reason is not None else APPROXIMATE_NOTICE

    def __len__(self) -> int:
        return len(self.results)


def not_delegated() -> SemanticGroup:
    """The gate declined, so nothing was asked and nothing is unavailable."""
    return SemanticGroup()


def unavailable(reason: UnavailabilityReason, detail: str = "") -> SemanticGroup:
    """The call was attempted or refused before it started, and this is why."""
    return SemanticGroup(
        delegated=True, reason=reason, detail=detail or UNAVAILABLE_SENTENCES[reason]
    )


# --------------------------------------------------------------------------
# The answer
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegatedSearch:
    """One query's two groups, exact first, never merged (D6).

    `local` is the whole of the local answer, unchanged — the same
    :class:`~cybercanon.application.use_cases.lookup_assets.SearchAnswer` the
    deterministic path returns on its own, so the existing surfaces keep
    reading the field they already read and this one is additive.
    """

    local: SearchAnswer
    semantic: SemanticGroup = field(default_factory=SemanticGroup)

    @property
    def term(self) -> str:
        return self.local.term

    @property
    def project(self) -> str | None:
        return self.local.project

    @property
    def exact(self) -> tuple[ExactResult, ...]:
        """The local cascade's hits, in its order, each stamped `EXACT`."""
        return tuple(ExactResult.of(hit) for hit in self.local.hits)

    @property
    def asset_ids(self) -> tuple[str, ...]:
        """The assets this query matched — **from the exact group only**.

        A semantic passage naming an asset does not put it here: the asset's own
        record is reachable through the exact results and nowhere else.
        """
        return self.local.asset_ids

    @property
    def groups(self) -> tuple[ProvenanceGroup[object], ...]:
        """The two presented groups, exact first, as the domain orders them."""
        return grouped_by_provenance(self.exact, self.semantic.results)

    @property
    def recorded_as_miss(self) -> bool:
        """Whether the local half recorded this term as a miss (D11, `asset-lookup`)."""
        return self.local.recorded_as_miss

    @property
    def was_delegated(self) -> bool:
        return self.semantic.delegated

    @property
    def unavailable_reason(self) -> UnavailabilityReason | None:
        return self.semantic.reason


# --------------------------------------------------------------------------
# The use case
# --------------------------------------------------------------------------


@as_result
def search_assets_and_docs(
    term: str,
    *,
    search_index: SearchIndex,
    platform: DocumentPlatform | None = None,
    credential: Credential = NO_CREDENTIAL,
    project: str | None = None,
    budget: timedelta = DEFAULT_BUDGET,
    workspace: str = "",
) -> DelegatedSearch:
    """The local cascade, then at most one delegated call bounded by the budget.

    The order is the guarantee (D5): `local` is fully computed — and a term that
    matched nothing is already recorded as a miss — before the platform is
    touched at all. Nothing below can change it, including every way the
    platform has of not answering.
    """
    local = search_assets.raising(term, search_index=search_index, project=project)
    if not should_delegate(term, local.hits):
        return DelegatedSearch(local=local, semantic=not_delegated())
    return DelegatedSearch(
        local=local,
        semantic=_delegated(
            term,
            platform=platform if platform is not None else NullDocumentPlatform(),
            credential=credential,
            budget=budget,
            workspace=workspace,
        ),
    )


def _delegated(
    term: str,
    *,
    platform: DocumentPlatform,
    credential: Credential,
    budget: timedelta,
    workspace: str,
) -> SemanticGroup:
    """One call, as the asker, or the reason there was not one.

    A caller with no forwardable credential is refused **here, before the
    request**, rather than having an anonymous request made for it: *"no query
    SHALL be made under a service credential on a person's behalf"*, and the
    honest way to satisfy that is for there to be no request.
    """
    if not credential.is_present:
        return unavailable(UnavailabilityReason.REJECTED, NO_AUTHORITY)
    try:
        passages = platform.search(term, credential, budget, workspace)
    except PlatformUnavailable as failure:
        return unavailable(failure.reason)
    except OperationFailed:
        return unavailable(UnavailabilityReason.UNREACHABLE)
    return SemanticGroup(
        results=tuple(SemanticResult.of(passage) for passage in passages), delegated=True
    )


__all__ = [
    "APPROXIMATE_NOTICE",
    "EXACT_LABEL",
    "GROUP_LABELS",
    "IDENTIFIER_SHAPE",
    "MINIMUM_PROSE_WORDS",
    "NO_AUTHORITY",
    "RESOLVING_KINDS",
    "SEMANTIC_LABEL",
    "UNAVAILABLE_SENTENCES",
    "DelegatedSearch",
    "ExactResult",
    "SemanticGroup",
    "SemanticResult",
    "is_identifier_shaped",
    "is_prose",
    "label_for",
    "not_delegated",
    "resolved_locally",
    "search_assets_and_docs",
    "should_delegate",
    "unavailable",
    "words_in",
]
