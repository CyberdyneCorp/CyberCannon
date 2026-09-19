/**
 * Task 2.3 — the invalidation map: what each write path makes untrue.
 *
 * D2 accepts one cost in so many words — *"a cache invalidation map that must
 * be kept honest, and a test per write path asserting what it invalidates"*.
 * This is the map. It is a total function over a closed set of write paths, so
 * a new write that forgets to declare its consequences does not compile, and
 * `tests/invalidation.test.ts` asserts, per path, exactly which cached
 * resources go and — just as importantly — which stay.
 *
 * Two rules decided here rather than at each call site:
 *
 * * **a listing is invalidated as a scope, not as a key.** The filters and the
 *   page are part of a listing's key, so invalidating the one combination the
 *   writer happened to be looking at would leave every other filtered view of
 *   the same project showing the old status.
 * * **a write only drops what it can change.** Dismissing a notification drops
 *   the person's unread items and nothing else: the request itself did not
 *   change, and dropping it would turn a read of a file into a read of the
 *   repository for no reason.
 */

import type { ResourceKey } from './resources';
import { key, resources, scopeOf } from './resources';

export const WRITE_PATHS = [
	'write-spec',
	'raise-request',
	'assign-request',
	'transition-request',
	'dismiss-notification'
] as const;
export type WritePath = (typeof WRITE_PATHS)[number];

export interface WriteTarget {
	readonly project: string;
	/** The asset a spec write landed on. */
	readonly asset?: string;
	/** The request an assignment, a transition or a dismissal names. */
	readonly request?: string;
}

/**
 * The resources one write makes untrue, as prefixes the cache can forget.
 *
 * Read it as a claim per path, because that is how it is tested:
 *
 * * **write-spec** — the asset's own specification, its compiled briefing and
 *   its recorded locations; the project's listing, because a status or an owner
 *   may have changed; every search over the project, because what a term
 *   matches is the specification; and every validation outcome in the project,
 *   because the rules an export is judged against are the ones just written.
 *   The *project* briefing stays: it is the standing rules under `.canon/`, and
 *   an asset's specification is not one of them.
 * * **raise-request** — the project's requests, and the unread items of the
 *   people the new request reached.
 * * **assign-request** / **transition-request** — the same two, plus the one
 *   request's own record.
 * * **dismiss-notification** — the unread items, and nothing else.
 */
export function invalidatedBy(path: WritePath, target: WriteTarget): readonly ResourceKey[] {
	switch (path) {
		case 'write-spec':
			return specWrite(target);
		case 'raise-request':
			return [scopeOf('requests', target.project), scopeOf('unread', target.project)];
		case 'assign-request':
		case 'transition-request':
			return [
				scopeOf('requests', target.project),
				scopeOf('unread', target.project),
				...(target.request ? [resources.request(target.project, target.request)] : [])
			];
		case 'dismiss-notification':
			return [scopeOf('unread', target.project)];
	}
}

function specWrite(target: WriteTarget): readonly ResourceKey[] {
	const { project, asset } = target;
	// Every lens of the one asset — `asset/<project>/<asset>` is a prefix of each
	// `.../lens=<name>` key — and never another asset's.
	const perAsset = asset
		? [
				key('asset', project, asset),
				resources.briefing(project, asset),
				resources.locations(project, asset)
			]
		: [scopeOf('asset', project), scopeOf('briefing', project), scopeOf('locations', project)];
	return [
		...perAsset,
		scopeOf('assets', project),
		scopeOf('search', project),
		scopeOf('validation', project)
	];
}
