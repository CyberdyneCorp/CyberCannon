import type { PageLoad } from './$types';
import type { Anchor } from '$lib/api';
import { CanonApi, annotationGateway, resources } from '$lib/api';
import { anchorPayload } from '$lib/annotation';
import type { AssetPage } from '$lib/asset';
import { BEFORE_READING, NO_VIEWER, assetScreen } from '$lib/asset';
import { readAssetAddress } from '$lib/address';
import { apiBaseUrl } from '$lib/config';
import { browser } from '$app/environment';
import { invalidateAll } from '$app/navigation';
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
			state: signedOut,
			annotations: null,
			annotationModel: null,
			viewer: NO_VIEWER,
			reanchor: async () => false,
			retryPreview: async () => {}
		};
	}
	const api = new CanonApi({ baseUrl: apiBaseUrl(), fetch, token: () => sessionStore.token() });
	const threads = annotationGateway(api);
	// The preview's bytes are read in the browser only: the mesh is handed to a
	// renderer the server does not have, and this `load` runs again there.
	const screen = await assetScreen(api, params.project, params.asset, url, {
		previewBytes: browser,
		viewImages: browser
	});
	return {
		...screen,
		annotationModel: threads,
		// Handed down as a bound function so the view performs the write without
		// ever holding a client: re-anchoring is an operation on an *anchor*, and
		// the anchor is the view's half of the 2D/3D boundary (D2).
		reanchor: async (annotation: string, anchor: Anchor) => {
			const written = await threads.reanchor(params.project, params.asset, annotation, {
				// Through `anchorPayload` like every other anchor a view produces:
				// `durable_key` is the server's to derive, so a client that sent one
				// would be proposing an identity for something it did not author.
				anchor: anchorPayload(anchor)
			});
			return written.ok;
		},
		// The retry `viewer-3d` requires beside an unloadable preview, and a real
		// one: the cache holds a refusal as firmly as it holds an answer (D2), so
		// the two preview entries are dropped before the route reads again.
		// Nothing else goes — the specification and the threads did not fail.
		retryPreview: async () => {
			api.cache.invalidate([
				resources.preview(params.project, params.asset),
				resources.previewContent(params.project, params.asset)
			]);
			await invalidateAll();
		}
	};
};
