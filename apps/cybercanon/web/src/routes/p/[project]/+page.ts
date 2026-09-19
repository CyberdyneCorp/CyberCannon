import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';
import { browserAddress } from '$lib/address';

/** A project's address is its browser. One screen, one address (D3). */
export const load: PageLoad = ({ params }) => {
	redirect(307, browserAddress({ project: params.project, query: '', filters: {}, page: null }));
};
