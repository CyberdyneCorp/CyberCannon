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
	'annotate',
	'promote-annotation',
	'link-document',
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
 * * **annotate** — creating, replying, editing, withdrawing, moving, re-anchoring,
 *   resolving or reopening: the asset's threads at every revision, its compiled
 *   briefing (an open issue appears in it and a settled one leaves it), its
 *   anchor resolutions (an anchor that moved resolves differently), and the
 *   project's triage queue. The preview *descriptor* stays: none of those
 *   changes an export, a count or a clip. The asset's *specification* stays, because none of
 *   those changes a declared field, and the project listing stays with it.
 * * **link-document** — linking, unlinking and create-and-link all write a
 *   reference into the specification, so they drop the asset's link list, the
 *   asset's own specification and its compiled briefing (a link is rendered in
 *   it as a bare address). The project listing and the searches stay: a link is
 *   not a status, an owner, a name or an alias, and dropping them would make
 *   every link a reason to re-read the repository.
 * * **promote-annotation** — everything `annotate` drops **and** everything a
 *   specification write drops, because a promotion is one: it writes a durable
 *   rule into `constraints` or `concept.silhouette_rules`, which changes what
 *   an export is judged against and what a search matches.
 */
export function invalidatedBy(path: WritePath, target: WriteTarget): readonly ResourceKey[] {
	switch (path) {
		case 'write-spec':
			return specWrite(target);
		case 'annotate':
			return annotationWrite(target);
		case 'promote-annotation':
			return [...annotationWrite(target), ...specWrite(target)];
		case 'link-document':
			return documentWrite(target);
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

function documentWrite(target: WriteTarget): readonly ResourceKey[] {
	const { project, asset } = target;
	const links = asset
		? [resources.documents(project, asset)]
		: [scopeOf('documents', project)];
	const spec = asset ? [key('asset', project, asset)] : [scopeOf('asset', project)];
	const briefing = asset ? [resources.briefing(project, asset)] : [scopeOf('briefing', project)];
	return [...links, ...spec, ...briefing];
}


function annotationWrite(target: WriteTarget): readonly ResourceKey[] {
	const { project, asset } = target;
	// `annotations/<project>/<asset>` is a prefix of every `.../rev=<revision>`
	// key, so one entry forgets the thread list at every revision it was read at.
	const threads = asset ? [key('annotations', project, asset)] : [scopeOf('annotations', project)];
	const briefing = asset ? [resources.briefing(project, asset)] : [scopeOf('briefing', project)];
	// A write that moves, re-anchors or withdraws an anchor changes which
	// annotations resolve against the current export, so the resolution listing
	// goes with the thread list. The preview *descriptor* stays: an annotation
	// write changes no export, no count and no clip.
	const resolutions = asset
		? [resources.resolutions(project, asset)]
		: [scopeOf('resolutions', project)];
	return [...threads, ...briefing, ...resolutions, scopeOf('triage', project)];
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
