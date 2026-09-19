import type { PageLoad } from './$types';
import { CanonApi } from '$lib/api';
import type { LensedSpec } from '$lib/api';
import { readAssetAddress } from '$lib/address';
import type { Surface } from '$lib/address';
import { apiBaseUrl } from '$lib/config';
import { screenFor } from '$lib/screen';
import { signedOutScreen } from '$lib/session/guard';
import { sessionStore } from '$lib/session/session';

const DEFAULT_SURFACES: readonly Surface[] = ['overview'];

/**
 * One asset, at the surface the address names.
 *
 * The address carries the project and the identifier the specification declares
 * — never a name and never an index row — so the link survives a rename and an
 * index rebuild, which is what `app-navigation` requires of it. A surface the
 * asset does not have degrades to its default view *and says why*.
 */
export const load: PageLoad = async ({ params, url, fetch }) => {
	const signedOut = signedOutScreen<LensedSpec>();
	if (signedOut) {
		return {
			address: readAssetAddress(params.project, params.asset, url, DEFAULT_SURFACES),
			available: DEFAULT_SURFACES,
			state: signedOut
		};
	}
	const api = new CanonApi({ baseUrl: apiBaseUrl(), fetch, token: () => sessionStore.token() });
	const result = await api.asset(params.project, params.asset);
	const available = surfacesOf(result.ok ? result.data : null);
	const address = readAssetAddress(params.project, params.asset, url, available);
	const state = screenFor<LensedSpec>(result, {
		unavailable: address.notice ? [address.notice] : []
	});
	return { address, available, state };
};

/**
 * Which surfaces this asset actually has.
 *
 * The sheet and the viewer are `add-model-sheet-2d` and `add-viewer-3d`; until
 * they exist, an asset has its overview and nothing else, and an address naming
 * one of the others degrades rather than failing — which is the behaviour
 * `app-navigation` specifies and the one this shell is here to guarantee.
 */
function surfacesOf(_spec: LensedSpec | null): readonly Surface[] {
	return DEFAULT_SURFACES;
}

