/**
 * The Model half of the application: the typed client, the one cache, and the
 * map that says what a write makes untrue.
 *
 * Views never call the API (openspec/project.md — *"Views never call the API
 * directly"*). They call something here, and everything here goes through the
 * cache, so the same asset's status cannot be held by three screens that
 * disagree after a promotion.
 */

import { CanonClient } from './client';
import type { ClientOptions } from './client';
import { QueryCache, queryCache } from './cache';
import type { ResourceKey } from './resources';
import { resources } from './resources';
import type { ListingFilters } from './resources';
import { invalidatedBy } from './invalidation';
import type { WritePath, WriteTarget } from './invalidation';
import type {
	ApiResult,
	AssetRow,
	LensedSpec,
	LocationAnswer,
	Page,
	SearchHit,
	StatusReport,
	ValidationOutcome
} from './types';

export * from './types';
export * from './resources';
export * from './invalidation';
export { CanonClient } from './client';
export { QueryCache, queryCache } from './cache';
export { routeStateFor, kindForStatus } from './outcomes';

export interface ApiOptions extends ClientOptions {
	readonly cache?: QueryCache;
}

/**
 * Reads served from the cache, writes that say what they invalidated.
 *
 * A read caches the whole :type:`ApiResult`, refusal included. A refusal is an
 * answer — *"you may not read this project"* does not become truer by being
 * asked again within one screen — and caching only successes would make every
 * forbidden screen a retry storm.
 */
export class CanonApi {
	readonly client: CanonClient;
	readonly cache: QueryCache;

	constructor(options: ApiOptions) {
		this.client = new CanonClient(options);
		this.cache = options.cache ?? queryCache;
	}

	/**
	 * Which projects this person may open — the one read that names no project.
	 *
	 * It is cached like any other read, so the switcher in the frame and a screen
	 * that wants to know whether an address belongs to a project it may open ask
	 * once between them (D2).
	 */
	status(): Promise<ApiResult<StatusReport>> {
		return this.cache.read(resources.projects(), () => this.client.readStatus());
	}

	assets(project: string, filters: ListingFilters = {}): Promise<ApiResult<Page<AssetRow>>> {
		return this.cache.read(resources.assets(project, filters), () =>
			this.client.listAssets(project, {
				...filters,
				page: filters.page ?? null,
				pageSize: filters.size
			})
		);
	}

	asset(project: string, asset: string, lens?: string): Promise<ApiResult<LensedSpec>> {
		return this.cache.read(resources.asset(project, asset, lens), () =>
			this.client.readAsset(project, asset, lens)
		);
	}

	locations(project: string, asset: string): Promise<ApiResult<LocationAnswer>> {
		return this.cache.read(resources.locations(project, asset), () =>
			this.client.readLocations(project, asset)
		);
	}

	/** One export in the repository, against the specification governing it. */
	validate(project: string, exportPath: string): Promise<ApiResult<ValidationOutcome>> {
		return this.cache.read(resources.validation(project, exportPath), () =>
			this.client.validate(project, exportPath)
		);
	}

	search(
		project: string,
		term: string,
		page: string | null = null
	): Promise<ApiResult<Page<SearchHit>>> {
		return this.cache.read(resources.search(project, term, page), () =>
			this.client.search(project, term, { page })
		);
	}

	/**
	 * Run a write and forget what it made untrue, in that order.
	 *
	 * The cache is dropped whatever the outcome: a refused write may still have
	 * moved the repository underneath us — a conflict says so by definition —
	 * and a cache kept after a conflict is a screen showing a revision that no
	 * longer exists.
	 */
	async write<T>(
		path: WritePath,
		target: WriteTarget,
		perform: (client: CanonClient) => Promise<ApiResult<T>>
	): Promise<{ readonly result: ApiResult<T>; readonly invalidated: readonly ResourceKey[] }> {
		const result = await perform(this.client);
		const invalidated = this.cache.invalidate(invalidatedBy(path, target));
		return { result, invalidated };
	}

	/** What signing out does: nothing of the previous session remains (`web-session`). */
	forgetEverything(): void {
		this.cache.clear();
	}
}
