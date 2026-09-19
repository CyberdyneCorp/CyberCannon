/**
 * Task 2.4 (D10) — the web application's readiness, and it is process-only.
 *
 * `deployment-operations` is explicit that this one may not reach the API:
 * *"the web application does not require the API to become ready"*. So this
 * handler calls nothing, fetches nothing and reads no configuration. It answers
 * because the process is up, which is the only thing its readiness is allowed
 * to mean — a readiness that called the API would turn an API outage into a
 * failed deploy of the application that is supposed to render the outage.
 *
 * The degraded shell is the other half of the same decision: a page whose data
 * cannot be fetched renders an explicit unavailable state (see
 * `$lib/api/availability.ts`) rather than an error or a blank screen.
 */
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { READY } from '$lib/readiness';

export const prerender = false;

export const GET: RequestHandler = () => json({ status: READY });
