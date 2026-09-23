"""The in-memory `SearchIndex` — rows in a dict, ranked by the port's cascade.

It is the fake the unit suite and the BDD steps run against, and the first half
of the conformance pair `SqliteSearchIndex` joins. Every ordering decision is
delegated to :func:`~cybercanon.application.ports.search_index.rank`, so the
fake cannot drift into being a second search engine — which is the failure the
conformance suites exist to catch one level up.

Misses are counted rather than appended, because the question they answer is
*which term do people keep asking for*, and a list with the same word forty
times answers it worse than a count does.
"""

from __future__ import annotations

from cybercanon.application.ports.search_index import (
    FileFingerprint,
    IndexedAsset,
    RecordedMiss,
    SearchHit,
    pending_suggestions,
    rank,
)
from cybercanon.domain.derived import DerivedRecord, SuggestionDecision


class InMemorySearchIndex:
    """Indexed assets keyed by project and identifier, with recorded misses."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], IndexedAsset] = {}
        self._misses: dict[tuple[str, str], RecordedMiss] = {}
        self._derived: dict[tuple[str, str], DerivedRecord] = {}
        self._decisions: dict[tuple[str, str, str], SuggestionDecision] = {}

    # -- writing ---------------------------------------------------------

    def upsert(self, entry: IndexedAsset) -> None:
        self._entries[(entry.project, entry.asset_id)] = entry

    def forget(self, asset_id: str, project: str | None = None) -> None:
        for key in self._keys(asset_id, project):
            self._entries.pop(key, None)

    def clear(self) -> None:
        """The index is disposable: deleting it loses nothing a rebuild cannot restore."""
        self._entries.clear()
        self._misses.clear()
        self._derived.clear()
        self._decisions.clear()

    # -- reading ---------------------------------------------------------

    def get(self, asset_id: str, project: str | None = None) -> IndexedAsset | None:
        keys = self._keys(asset_id, project)
        return self._entries[keys[0]] if keys else None

    def list_assets(
        self,
        project: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
    ) -> tuple[IndexedAsset, ...]:
        return tuple(
            sorted(
                (
                    entry
                    for entry in self._scoped(project)
                    if _matches(entry, status=status, owner=owner, tag=tag)
                ),
                key=lambda entry: entry.asset_id,
            )
        )

    def search(self, term: str, project: str | None = None) -> tuple[SearchHit, ...]:
        return rank(self._scoped(project), term, self._suggestions(project))

    def is_stale(self, asset_id: str, current: FileFingerprint | None) -> bool:
        entry = self.get(asset_id)
        return entry is None or entry.fingerprint != current

    # -- misses (D11) ----------------------------------------------------

    def record_miss(self, term: str, project: str | None = None) -> None:
        scope = project or ""
        key = (scope, term.strip().lower())
        recorded = self._misses.get(key)
        self._misses[key] = RecordedMiss(
            term=recorded.term if recorded else term,
            project=scope,
            count=recorded.count + 1 if recorded else 1,
        )

    def misses(self, project: str | None = None) -> tuple[RecordedMiss, ...]:
        return tuple(
            sorted(
                (
                    miss
                    for (scope, _), miss in self._misses.items()
                    if project is None or scope == project
                ),
                key=lambda miss: (miss.project, miss.term),
            )
        )

    # -- derived metadata (add-derived-metadata) -------------------------

    def put_derived(self, record: DerivedRecord, project: str = "") -> None:
        """Keyed by the image's content hash, so a regeneration lands on itself."""
        self._derived[(project, record.source_hash)] = record

    def derived(self, source_hash: str, project: str | None = None) -> DerivedRecord | None:
        found = [
            record
            for (scope, held), record in sorted(self._derived.items())
            if held == source_hash and (project is None or scope == project)
        ]
        return found[0] if found else None

    def derived_records(
        self, project: str | None = None, asset_id: str | None = None
    ) -> tuple[DerivedRecord, ...]:
        return tuple(
            record
            for (scope, _), record in sorted(self._derived.items())
            if (project is None or scope == project)
            and (asset_id is None or record.asset_id == asset_id)
        )

    def record_decision(self, decision: SuggestionDecision, project: str = "") -> None:
        self._decisions[(project, *decision.key)] = decision

    def decisions(
        self, source_hash: str | None = None, project: str | None = None
    ) -> tuple[SuggestionDecision, ...]:
        return tuple(
            decision
            for (scope, held, _), decision in sorted(self._decisions.items())
            if (project is None or scope == project)
            and (source_hash is None or held == source_hash)
        )

    def clear_derived(self, project: str | None = None) -> None:
        """Drop the generated half. Accepted aliases are in the files, untouched."""
        for key in [key for key in self._derived if project is None or key[0] == project]:
            self._derived.pop(key, None)
        for key in [key for key in self._decisions if project is None or key[0] == project]:
            self._decisions.pop(key, None)

    # -- internals -------------------------------------------------------

    def _suggestions(self, project: str | None):
        """The sixth pass's input: every asset's pending suggested aliases (D9)."""
        return pending_suggestions(self.derived_records(project), self.decisions(project=project))

    def _scoped(self, project: str | None) -> tuple[IndexedAsset, ...]:
        return tuple(
            entry
            for (scope, _), entry in self._entries.items()
            if project is None or scope == project
        )

    def _keys(self, asset_id: str, project: str | None) -> tuple[tuple[str, str], ...]:
        return tuple(
            key
            for key in sorted(self._entries)
            if key[1] == asset_id and (project is None or key[0] == project)
        )


def _matches(entry: IndexedAsset, status: str | None, owner: str | None, tag: str | None) -> bool:
    """Every filter given must hold — filters combine, they do not widen."""
    if status is not None and (entry.status or "").lower() != status.lower():
        return False
    if owner is not None and not entry.owned_by(owner):
        return False
    return not (tag is not None and not _has_tag(entry, tag))


def _has_tag(entry: IndexedAsset, tag: str) -> bool:
    wanted = tag.strip().lower()
    return any(held.strip().lower() == wanted for held in entry.tags)


__all__ = ["InMemorySearchIndex"]
