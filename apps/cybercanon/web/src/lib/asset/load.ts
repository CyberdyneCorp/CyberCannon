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
	AnchorResolutions,
	AnnotationListing,
	ApiResult,
	DocumentListing,
	Failure,
	LensedSpec,
	LocationAnswer,
	PreviewContent,
	PreviewDescriptor,
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
	annotations?(project: string, asset: string): Promise<ApiResult<AnnotationListing>>;
	documents?(project: string, asset: string): Promise<ApiResult<DocumentListing>>;
	preview?(project: string, asset: string): Promise<ApiResult<PreviewDescriptor>>;
	previewContent?(project: string, asset: string): Promise<ApiResult<PreviewContent>>;
	anchorResolutions?(project: string, asset: string): Promise<ApiResult<AnchorResolutions>>;
}

/**
 * What the 3D viewer needs, read by the route so the view reaches no API (D2).
 *
 * `null` on every other surface. The bytes travel base64 exactly as the surface
 * renders them and are decoded once, here, so the component is handed a buffer
 * and never learns what an encoding is.
 */
export interface ViewerReads {
	readonly descriptor: PreviewDescriptor | null;
	readonly resolutions: AnchorResolutions | null;
	readonly bytes: ArrayBuffer | null;
	/** Why the preview's bytes could not be read, when the descriptor named one. */
	readonly unloadable: string | null;
}

export const NO_VIEWER: ViewerReads = {
	descriptor: null,
	resolutions: null,
	bytes: null,
	unloadable: null
};

/** The address as this asset resolves it, and the screen at it. */
export interface AssetScreen {
	readonly address: {
		readonly project: string;
		readonly asset: string;
		readonly surface: Surface;
		/** The thread the address opens on, when the triage pass linked to one. */
		readonly annotation?: string;
	};
	readonly available: readonly Surface[];
	readonly state: RouteState<AssetPage>;
	/**
	 * The asset's threads, read only when the sheet is the surface being opened.
	 *
	 * The route reads them so the sheet does not: *"views never call the API
	 * directly"*, and the ViewModel is handed what the route already has (D9).
	 * `null` on every other surface, because a screen that does not show threads
	 * should not be paying for them.
	 */
	readonly annotations?: AnnotationListing | null;
	/**
	 * The documents linked to this asset and to its project, as this person
	 * sees them.
	 *
	 * Read by the route like everything else, and **never fatal**: a platform
	 * that is down changes what each link says about itself and nothing about
	 * whether the asset has a page. A deployment with no document platform at
	 * all still answers this — with every link unresolved and the reason named
	 * — which is the degradation requirement, not a special case.
	 */
	readonly documents?: DocumentListing | null;
	/** What the 3D viewer needs, read only when the viewer is what is being opened. */
	readonly viewer?: ViewerReads;
}

/** The surfaces an asset has before anything has been read about it. */
export const BEFORE_READING: readonly Surface[] = ['overview'];

/** What a caller can ask the asset screen to leave out. One entry, for one reason. */
export interface AssetOptions {
	/**
	 * Whether to read the preview's bytes.
	 *
	 * `false` during server rendering. The descriptor, the orphan count and every
	 * sentence the viewer states are all read either way — what is skipped is the
	 * one expensive thing, and it is the one thing only a browser can use: the
	 * mesh is handed to a renderer that does not exist on the server, and the
	 * universal `load` runs again in the browser, which is where it is fetched.
	 */
	readonly previewBytes?: boolean;
}

export async function assetScreen(
	api: AssetReads,
	project: string,
	asset: string,
	url: URL,
	options: AssetOptions = {}
): Promise<AssetScreen> {
	const locations = await api.locations(project, asset);
	if (!locations.ok) return refused(project, asset, url, locations.failure);
	const spec = await api.asset(project, asset);
	if (!spec.ok) return refused(project, asset, url, spec.failure);
	const validation = await verdict(api, project, locations.data);
	const page = assetPage({
		project,
		locations: locations.data,
		document: spec.data.full,
		validation
	});
	const available = availableSurfaces(page);
	const address = readAssetAddress(project, asset, url, available);
	const state = screenFor<AssetPage>(
		{ ok: true, data: page, freshness: locations.freshness },
		{ unavailable: disclosures(address.notice, locations.data) }
	);
	return {
		address,
		available,
		state,
		annotations: await threads(api, project, asset, address.surface),
		documents: await links(api, project, asset),
		viewer: await viewerReads(api, project, asset, address.surface, options)
	};
}


/**
 * The link list, read on every surface and fatal on none.
 *
 * A refusal degrades to `null` rather than to a failed page: *"no unresolvable
 * link SHALL cause the asset, its specification or the remainder of its links
 * to fail to display"*, and a read that could not be made at all is the
 * strongest form of that.
 */
async function links(
	api: AssetReads,
	project: string,
	asset: string
): Promise<DocumentListing | null> {
	if (!api.documents) return null;
	const listing = await api.documents(project, asset);
	return listing.ok ? listing.data : null;
}

/**
 * The preview descriptor, the orphan count and the preview's bytes.
 *
 * Read here rather than in the component for the reason every other read is:
 * *"views never call the API directly"*, and the query cache is the one place
 * server state lives (D2). The descriptor and the resolutions are read even
 * when there is no preview — the descriptor is what *carries* the reason there
 * is none, and the orphan count is answerable with no renderer at all (D6).
 */
async function viewerReads(
	api: AssetReads,
	project: string,
	asset: string,
	surface: Surface,
	options: AssetOptions
): Promise<ViewerReads> {
	if (surface !== 'viewer' || !api.preview) return NO_VIEWER;
	const described = await api.preview(project, asset);
	if (!described.ok) return NO_VIEWER;
	const resolutions = api.anchorResolutions
		? await api.anchorResolutions(project, asset)
		: null;
	const wanted = options.previewBytes ?? true;
	const content =
		wanted && described.data.preview && api.previewContent
			? await api.previewContent(project, asset)
			: null;
	return {
		descriptor: described.data,
		resolutions: resolutions?.ok ? resolutions.data : null,
		bytes: content?.ok ? decode(content.data.content) : null,
		unloadable: content && !content.ok ? content.failure.message : null
	};
}

/** The preview's bytes, decoded once. The component is handed a buffer. */
function decode(base64: string): ArrayBuffer {
	const binary = atob(base64);
	const bytes = new Uint8Array(binary.length);
	for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
	return bytes.buffer;
}

/** The asset's threads, when the sheet is what is being opened, and never otherwise. */
async function threads(
	api: AssetReads,
	project: string,
	asset: string,
	surface: Surface
): Promise<AnnotationListing | null> {
	// Both annotating surfaces need them, and for the same reason: the threads
	// are the valuable half, and the viewer lists them — orphans included —
	// whether or not anything renders (D11).
	if ((surface !== 'sheet' && surface !== 'viewer') || !api.annotations) return null;
	const listing = await api.annotations(project, asset);
	return listing.ok ? listing.data : null;
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
