/**
 * How server state is named. One resource, one key, everywhere.
 *
 * D2 puts server state in a single cache keyed by resource; a key that two
 * callers spell differently is two caches with one name, which is the failure
 * D2 exists to prevent. So nothing builds a key by hand — every key comes from
 * here, and every key begins with a scope and a project so that invalidation
 * can name *"everything the listing of this project is"* without enumerating
 * the filter combinations somebody happened to have opened.
 *
 * Segments are percent-encoded before they are joined, so a separator inside an
 * identifier cannot make one key look like another key's prefix.
 */

export const SCOPES = [
	'assets',
	'asset',
	'briefing',
	'locations',
	'search',
	'project-briefing',
	'validation',
	'requests',
	'request',
	'unread'
] as const;
export type Scope = (typeof SCOPES)[number];

export type ResourceKey = string & { readonly __resource?: unique symbol };

const SEPARATOR = '/';

export function key(
	scope: Scope,
	project: string,
	...rest: (string | null | undefined)[]
): ResourceKey {
	const parts = [scope, project, ...rest.filter((part): part is string => Boolean(part))];
	return parts.map(encodeURIComponent).join(SEPARATOR) as ResourceKey;
}

/** Everything under one scope of one project — what a write invalidates. */
export function scopeOf(scope: Scope, project: string): ResourceKey {
	return key(scope, project);
}

export function isUnder(candidate: ResourceKey, prefix: ResourceKey): boolean {
	return candidate === prefix || candidate.startsWith(`${prefix}${SEPARATOR}`);
}

/** The filters a listing key carries, spelled in one order so two callers agree. */
export interface ListingFilters {
	readonly status?: string;
	readonly owner?: string;
	readonly tag?: string;
	readonly page?: string | null;
	/**
	 * How many rows were asked for, when a caller asked for more than the default.
	 *
	 * It is part of the key because it is part of the answer: the browser reads
	 * one page for the screen and a full page for the filter membership behind a
	 * search, and two different answers under one key would be one of them
	 * silently serving the other.
	 */
	readonly size?: number;
}

export const resources = {
	assets(project: string, filters: ListingFilters = {}): ResourceKey {
		return key(
			'assets',
			project,
			`status=${filters.status ?? ''}`,
			`owner=${filters.owner ?? ''}`,
			`tag=${filters.tag ?? ''}`,
			`page=${filters.page ?? ''}`,
			`size=${filters.size ?? ''}`
		);
	},
	asset(project: string, asset: string, lens?: string): ResourceKey {
		return key('asset', project, asset, `lens=${lens ?? ''}`);
	},
	briefing(project: string, asset: string): ResourceKey {
		return key('briefing', project, asset);
	},
	locations(project: string, asset: string): ResourceKey {
		return key('locations', project, asset);
	},
	search(project: string, term: string, page?: string | null): ResourceKey {
		return key('search', project, `q=${term}`, `page=${page ?? ''}`);
	},
	projectBriefing(project: string): ResourceKey {
		return key('project-briefing', project);
	},
	validation(project: string, exportPath: string): ResourceKey {
		return key('validation', project, exportPath);
	},
	requests(project: string): ResourceKey {
		return key('requests', project);
	},
	request(project: string, request: string): ResourceKey {
		return key('request', project, request);
	},
	unread(project: string): ResourceKey {
		return key('unread', project);
	}
} as const;
