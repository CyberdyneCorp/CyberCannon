/**
 * The root screen's data, which is one question: is the API answering?
 *
 * It is a `load` rather than something the screen does, because D6 makes the
 * unavailable case a *route state* rather than a conditional inside a
 * component — and because a load that threw would be exactly what D10 forbids
 * while the API is down.
 */
import type { PageLoad } from './$types';
import { apiAvailability } from '$api/availability';
import { apiBaseUrl } from '$lib/config';

export const load: PageLoad = async ({ fetch }) => ({
	state: await apiAvailability(fetch, apiBaseUrl())
});
