/**
 * D3 — the address is the state.
 *
 * Project, asset, surface, filters and query all live in the URL, and nothing
 * a reload should preserve is held in a component. `app-navigation` requires a
 * shared link to reopen what the sharer was looking at and `asset-browser`
 * requires a filtered listing to be shareable; both are satisfied here by
 * construction rather than by a synchronisation routine that drifts.
 *
 * Every function in this module is total and pure: an address in, a value out,
 * or a value in and an address out. Reading an address never fails — an
 * unreadable fragment degrades to the default (`app-navigation`: *"state that
 * cannot be restored SHALL degrade to the asset's default view rather than to
 * an error"*), and it says so, so the person can be told why.
 */

/** The surfaces an asset can be opened on. A closed set: an unknown one degrades. */
export const SURFACES = ['overview', 'sheet', 'viewer'] as const;
export type Surface = (typeof SURFACES)[number];

/** What an address names when it names no surface. */
export const DEFAULT_SURFACE: Surface = 'overview';

/** The filters `asset-lookup` specifies, and the only ones the address carries. */
export const FILTERS = ['status', 'owner', 'tag'] as const;
export type FilterName = (typeof FILTERS)[number];

export type Filters = Partial<Record<FilterName, string>>;

/** Everything the browser screen is, as the address holds it. */
export interface BrowserAddress {
	readonly project: string;
	readonly query: string;
	readonly filters: Filters;
	readonly page: string | null;
}

/** Everything an asset screen is, as the address holds it. */
export interface AssetAddress {
	readonly project: string;
	readonly asset: string;
	readonly surface: Surface;
}

/** A surface read back from an address, and whether it was the one that was asked for. */
export interface ResolvedSurface {
	readonly surface: Surface;
	readonly notice: string | null;
}

export function isSurface(value: string): value is Surface {
	return (SURFACES as readonly string[]).includes(value);
}

export function projectAddress(project: string): string {
	return `/p/${encodeURIComponent(project)}`;
}

/** The browser, with its query and filters written into the address. */
export function browserAddress(address: BrowserAddress): string {
	const parameters = new URLSearchParams();
	if (address.query) parameters.set('q', address.query);
	for (const name of FILTERS) {
		const value = address.filters[name];
		if (value) parameters.set(name, value);
	}
	if (address.page) parameters.set('page', address.page);
	const search = parameters.toString();
	return `${projectAddress(address.project)}/assets${search ? `?${search}` : ''}`;
}

/**
 * An asset's address: the project and the identifier the specification declares.
 *
 * Never its name, never its position in a listing, never an index row id — so
 * the link survives a rename and an index rebuild, which is what
 * `app-navigation` requires of it.
 */
export function assetAddress(address: AssetAddress): string {
	const path = `${projectAddress(address.project)}/a/${encodeURIComponent(address.asset)}`;
	return address.surface === DEFAULT_SURFACE ? path : `${path}?surface=${address.surface}`;
}

/** The browser address a URL names. Unknown parameters are simply not carried. */
export function readBrowserAddress(project: string, url: URL): BrowserAddress {
	const filters: Record<string, string> = {};
	for (const name of FILTERS) {
		const value = url.searchParams.get(name)?.trim();
		if (value) filters[name] = value;
	}
	return {
		project,
		query: url.searchParams.get('q')?.trim() ?? '',
		filters,
		page: url.searchParams.get('page') || null
	};
}

/** The same address with one filter removed — the affordance beside each chip. */
export function withoutFilter(address: BrowserAddress, name: FilterName): BrowserAddress {
	const filters = { ...address.filters };
	delete filters[name];
	return { ...address, filters, page: null };
}

/** The same address with every filter removed, which the empty screen offers. */
export function withoutFilters(address: BrowserAddress): BrowserAddress {
	return { ...address, filters: {}, page: null };
}

/** Which filters are on, in the order they are specified, for a screen to render. */
export function activeFilters(address: BrowserAddress): readonly { name: FilterName; value: string }[] {
	return FILTERS.filter((name) => address.filters[name]).map((name) => ({
		name,
		value: address.filters[name] as string
	}));
}

/**
 * The surface an address names, degraded to the default when it names none.
 *
 * `available` is what the asset actually has. A surface that no longer exists
 * degrades *and says so*: `app-navigation` requires the person to be told why,
 * and a silent degrade is indistinguishable from the link never having worked.
 */
export function resolveSurface(
	named: string | null,
	available: readonly Surface[] = SURFACES
): ResolvedSurface {
	if (!named) return { surface: DEFAULT_SURFACE, notice: null };
	if (!isSurface(named)) {
		return { surface: DEFAULT_SURFACE, notice: unknownSurface(named) };
	}
	if (!available.includes(named)) {
		return { surface: DEFAULT_SURFACE, notice: absentSurface(named) };
	}
	return { surface: named, notice: null };
}

export function readAssetAddress(
	project: string,
	asset: string,
	url: URL,
	available: readonly Surface[] = SURFACES
): AssetAddress & { readonly notice: string | null } {
	const resolved = resolveSurface(url.searchParams.get('surface'), available);
	return { project, asset, surface: resolved.surface, notice: resolved.notice };
}

function unknownSurface(named: string): string {
	return (
		`this address names a surface called ${JSON.stringify(named)}, which this ` +
		`application does not have; showing the asset's default view instead`
	);
}

function absentSurface(named: Surface): string {
	return (
		`this address names the ${named} surface, which this asset no longer has; ` +
		`showing its default view instead`
	);
}
