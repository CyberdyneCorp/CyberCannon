/**
 * The asset screen, resolved to one member of the closed set (D6).
 *
 * The route's `load` is a handful of lines and this is the rest of it, out here
 * where it runs without SvelteKit. It performs the reads, arranges them with
 * :func:`assetPage`, and resolves the address's surface against the surfaces
 * the asset turns out to have — in that order, because *which* surfaces exist
 * is an answer about the asset, not about the address.
 *
 * **Two failures, treated differently, and the difference is the point.**
 *
 * * The locations and the compiled briefing are the page. If either cannot be
 *   read, the page is the failure — not a page with empty sections. The
 *   absence-is-stated rule cuts both ways: a page that said *"no constraint is
 *   in effect"* because the briefing would not compile would be stating an
 *   absence that is not true.
 * * The verdict on a recorded export is not the page. It is one section's last
 *   three lines, and when it cannot be read the section says so and the rest of
 *   the asset is still there.
 */

import type { Surface } from '$lib/address';
import { readAssetAddress } from '$lib/address';
import type {
	ApiResult,
	Failure,
	LensedSpec,
	LocationAnswer,
	ValidationOutcome
} from '$lib/api';
import { routeStateFor } from '$lib/api';
import { degraded, type RouteState } from '$lib/route-state';
import { screenFor } from '$lib/screen';
import type { AssetPage } from './page';
import { VALIDATED_EXPORT, assetPage, availableSurfaces } from './page';

/** What the asset screen needs from the Model — one client and one cache behind it. */
export interface AssetReads {
	locations(project: string, asset: string): Promise<ApiResult<LocationAnswer>>;
	asset(project: string, asset: string, lens?: string): Promise<ApiResult<LensedSpec>>;
	validate(project: string, exportPath: string): Promise<ApiResult<ValidationOutcome>>;
}

/** The address as this asset resolves it, and the screen at it. */
export interface AssetScreen {
	readonly address: { readonly project: string; readonly asset: string; readonly surface: Surface };
	readonly available: readonly Surface[];
	readonly state: RouteState<AssetPage>;
}

/** The surfaces an asset has before anything has been read about it. */
export const BEFORE_READING: readonly Surface[] = ['overview'];

export async function assetScreen(
	api: AssetReads,
	project: string,
	asset: string,
	url: URL
): Promise<AssetScreen> {
	const locations = await api.locations(project, asset);
	if (!locations.ok) return refused(project, asset, url, locations.failure);
	const spec = await api.asset(project, asset);
	if (!spec.ok) return refused(project, asset, url, spec.failure);
	const validation = await verdict(api, project, locations.data);
	const page = assetPage({ project, locations: locations.data, document: spec.data.full, validation });
	const available = availableSurfaces(page);
	const address = readAssetAddress(project, asset, url, available);
	const state = screenFor<AssetPage>(
		{ ok: true, data: page, freshness: locations.freshness },
		{ unavailable: disclosures(address.notice, locations.data) }
	);
	return { address, available, state };
}

/**
 * The verdict on the export `where_is` reports, or nothing to ask about.
 *
 * Asked for by path, which is the address `http-api` validates by — the same
 * export the G2 writer recorded — so the page cannot show a verdict for one
 * export beside the path of another.
 *
 * **A gap in `http-api`, recorded rather than worked around.** G2 makes the
 * outcome repository content: the worker writes it beside the specification and
 * the index carries the export and the date, which is where the two lines above
 * this one come from. What no read exposes is the *recorded verdict* — so the
 * only way to show one is `GET /validations`, which re-validates the export at
 * the served revision. That is the same `validate_export` every other surface
 * runs, so it cannot disagree with them; but G1 put validation outside the
 * request path because mesh loading is unbounded work, and this read puts a
 * small piece of it back. The cache keeps it to once per asset per session, and
 * the fix belongs in `http-api` as a read of the recorded outcome, not in a
 * second verdict invented here.
 */
async function verdict(
	api: AssetReads,
	project: string,
	locations: LocationAnswer
): Promise<ApiResult<ValidationOutcome> | null> {
	const recorded = locations.locations.find((entry) => entry.label === VALIDATED_EXPORT);
	if (!recorded?.recorded) return null;
	return api.validate(project, recorded.value);
}

/** What the screen has to disclose beside its content, in the order it says it. */
function disclosures(notice: string | null, locations: LocationAnswer): readonly string[] {
	return [...(notice ? [notice] : []), ...(locations.stale ? [locations.notice] : [])];
}

/**
 * A refusal as a screen, with the address still resolved.
 *
 * `app-navigation` requires *"not found"* and *"not permitted"* to be different
 * screens and neither to reveal anything about an asset the person may not
 * read, which is why nothing about the asset is loaded on this path: the only
 * thing the screen knows is the identifier the person themselves opened.
 */
function refused(project: string, asset: string, url: URL, failure: Failure): AssetScreen {
	return {
		address: readAssetAddress(project, asset, url, BEFORE_READING),
		available: BEFORE_READING,
		state:
			failure.kind === 'unavailable'
				? degraded<AssetPage>(null, [failure.subject ?? failure.identifier], failure.message)
				: routeStateFor<AssetPage>(failure)
	};
}
