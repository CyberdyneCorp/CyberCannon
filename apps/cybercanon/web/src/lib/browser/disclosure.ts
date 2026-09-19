/**
 * Task 4.5 — how a result matched, said out loud.
 *
 * `asset-browser`: *"Where a result matched on something other than its name or
 * identifier — an alias, a tag, a description, or an unaccepted suggestion —
 * the listing SHALL say so."* A person who searched for `scavenger` and got
 * `mech_scout` back has no way to tell whether the tool understood them or
 * guessed, and a result whose reason is invisible is a result nobody trusts.
 *
 * The vocabulary is the API's, not this application's: `matched` carries the
 * pass of the cascade that found the result, spelled by
 * `cybercanon.application.ports.search_index.MatchKind`. Nothing here re-derives
 * *why* something matched — that would be a second opinion about a ranking
 * `asset-lookup` already owns — it only translates the pass into a sentence.
 *
 * An unaccepted suggestion is the one entry with no implementation behind it
 * yet: `add-derived-metadata` specifies suggested aliases as *"a lowest-priority
 * fallback"* whose results *"SHALL be marked as matched on an unaccepted
 * suggestion"*, and the pass that produces them lands with that change. The
 * disclosure is written now because the screen that has to carry it is this one,
 * and because an unknown pass degrades to being disclosed verbatim rather than
 * to silence — the failure this whole module exists to prevent.
 */

/** The passes `asset-lookup` already runs, in the cascade's order. */
export const EXACT_ID = 'exact_id';
export const NAME_PREFIX = 'name_prefix';
export const ALIAS = 'alias';
export const TAG = 'tag';
export const DESCRIPTION = 'description';

/** The lowest-priority pass `add-derived-metadata` adds. Not yet produced. */
export const SUGGESTED_ALIAS = 'suggested_alias';

/** What a result matched on when that is the name or the identifier: nothing to say. */
export const NAMED = [EXACT_ID, NAME_PREFIX] as const;

export interface Disclosure {
	/** The pass, exactly as the surface spelled it. */
	readonly matched: string;
	/** What the screen says about it. */
	readonly text: string;
	/** Whether the match came from something nobody has accepted into the canon. */
	readonly unaccepted: boolean;
}

const SENTENCES: Readonly<Record<string, string>> = {
	[ALIAS]: 'matched an alias, not its name',
	[TAG]: 'matched a tag',
	[DESCRIPTION]: 'matched its description',
	[SUGGESTED_ALIAS]: 'matched an unaccepted suggested alias'
};

/**
 * What to say about how this result matched, or `null` when there is nothing
 * to say because it matched the name or the identifier the person typed.
 */
export function disclosureOf(matched: string): Disclosure | null {
	if ((NAMED as readonly string[]).includes(matched)) return null;
	return {
		matched,
		text: SENTENCES[matched] ?? `matched on ${matched}`,
		unaccepted: matched === SUGGESTED_ALIAS
	};
}

/** Whether this result exists only because of a proposal nobody accepted. */
export function isUnaccepted(matched: string): boolean {
	return disclosureOf(matched)?.unaccepted === true;
}
