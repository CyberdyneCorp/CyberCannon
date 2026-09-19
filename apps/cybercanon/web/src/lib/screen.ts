/**
 * Task 2.4 — one API outcome becomes one route state, in one place.
 *
 * Every data-bearing route ends here, which is what makes D6's set closed in
 * practice rather than in principle: a screen cannot be reached by a path that
 * skipped the translation, because there is only the one.
 *
 * Two things happen that a plain failure mapping would not do:
 *
 * * **a successful read of a working copy that may be stale is `degraded`, not
 *   `content`.** `hosted-repository` requires the staleness window to be
 *   visible, and a screen that rendered a stale answer as current would be the
 *   place that requirement quietly stopped holding.
 * * **emptiness is the caller's judgement, not this module's.** Only the screen
 *   knows whether nothing came back because the project has no assets, because
 *   the query matched nothing, or because the filters excluded what it matched
 *   — `asset-browser` requires three different screens for those.
 */

import type { ApiResult } from './api/types';
import { routeStateFor } from './api/outcomes';
import type { Empty, RouteState } from './route-state';
import { content, degraded } from './route-state';

export interface ScreenOptions<T> {
	/** Returns the empty screen this data means, or `null` when it is content. */
	readonly emptiness?: (data: T) => Empty | null;
	/** What else could not be served, named, so it is disclosed rather than hidden. */
	readonly unavailable?: readonly string[];
}

const STALE = 'this project was last confirmed against its remote earlier; it may be out of date';

export function screenFor<T>(
	result: ApiResult<T>,
	options: ScreenOptions<T> = {}
): RouteState<T> {
	if (!result.ok) return routeStateFor<T>(result.failure);
	const nothing = options.emptiness?.(result.data) ?? null;
	if (nothing) return nothing;
	const unavailable = [...(options.unavailable ?? [])];
	if (result.freshness?.mayBeStale) unavailable.push(STALE);
	if (unavailable.length > 0) {
		return degraded(result.data, unavailable, unavailable.join('; '));
	}
	return content(result.data);
}
