/**
 * The approximate half of a search, read off the envelope and rendered honestly.
 *
 * `semantic-search-delegation` asks for one thing of this application and it is
 * not ranking: *"the two SHALL be presented as distinct labelled groups with
 * exact matches ordered before semantic ones, and SHALL NOT be merged into a
 * single ranking or a single relevance score"*, and every passage *"SHALL name
 * the document it came from and SHALL be labelled as an approximate match
 * rather than a definitive answer"*.
 *
 * So there is nothing here that sorts, scores or interleaves. The exact rows
 * are the browser's rows and stay exactly where they are; this reads the second
 * group as the surface stated it, and says one of three things about it:
 *
 * * **it answered** — the passages, under a label that says approximate;
 * * **nothing was asked** — the query resolved locally or was not prose, so the
 *   group is simply absent rather than empty-looking;
 * * **it could not answer** — the reason, in the surface's own sentence, shown
 *   beside results that are still there. `asset-browser`: *"exact results SHALL
 *   still be shown"* and *"the screen SHALL state that the semantic results are
 *   unavailable"*.
 *
 * Nothing here decides *whether* a query was delegated. That is the API's
 * answer; this only says it in a sentence a person can act on.
 */

import type { ApiResult, Passage, SemanticGroup } from '$lib/api';

/** What an answer with no approximate half at all looks like. */
export const NOTHING_DELEGATED: SemanticGroup = {
	label: 'approximate matches from linked documents',
	approximate: true,
	delegated: false,
	available: true,
	reason: null,
	notice: '',
	results: []
};

/** The approximate group the surface stated, or the absent one. */
export function semanticOf(result: ApiResult<unknown>): SemanticGroup {
	if (!result.ok) return NOTHING_DELEGATED;
	const declared = result.beside?.semantic;
	return isGroup(declared) ? declared : NOTHING_DELEGATED;
}

/** Whether this group is worth a heading at all — it answered, or it could not. */
export function isShown(group: SemanticGroup): boolean {
	return group.delegated;
}

/** What the screen says about the group: its notice, or nothing. */
export function noteOf(group: SemanticGroup): string {
	return group.delegated ? group.notice : '';
}

/** What one passage is titled by — never an asset identifier, because it is not one. */
export function sourceOf(passage: Passage): string {
	return passage.source || passage.title || passage.url;
}

function isGroup(value: unknown): value is SemanticGroup {
	if (typeof value !== 'object' || value === null) return false;
	const candidate = value as Record<string, unknown>;
	return (
		typeof candidate.label === 'string' &&
		typeof candidate.available === 'boolean' &&
		typeof candidate.delegated === 'boolean' &&
		Array.isArray(candidate.results)
	);
}
