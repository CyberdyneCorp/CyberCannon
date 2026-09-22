import type { PageLoad } from './$types';
import { CanonApi } from '$lib/api';
import type { AssetPage } from '$lib/asset';
import { BEFORE_READING, assetScreen } from '$lib/asset';
import { readAssetAddress } from '$lib/address';
import { apiBaseUrl } from '$lib/config';
import { signedOutScreen } from '$lib/session/guard';
import { sessionStore } from '$lib/session/session';

/**
 * One asset, at the surface the address names.
 *
 * The address carries the project and the identifier the specification declares
 * — never a name and never an index row — so the link survives a rename and an
 * index rebuild, which is what `app-navigation` requires of it. A surface the
 * asset does not have degrades to its default view *and says why*.
 *
 * Nothing is asked of the surface on behalf of a person with no session
 * (`web-session`), and nothing about the asset is read on the path where the
 * answer is a refusal — which is how *"not permitted"* stays a screen that
 * knows nothing but the identifier the person themselves opened.
 */
export const load: PageLoad = async ({ params, url, fetch }) => {
	const signedOut = signedOutScreen<AssetPage>();
	if (signedOut) {
		return {
			address: readAssetAddress(params.project, params.asset, url, BEFORE_READING),
			available: BEFORE_READING,
			state: signedOut
		};
	}
	const api = new CanonApi({ baseUrl: apiBaseUrl(), fetch, token: () => sessionStore.token() });
	return assetScreen(api, params.project, params.asset, url);
};
