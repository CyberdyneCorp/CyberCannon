/**
 * Task 8.1 (D2) — the web application's liveness, and it is a constant.
 *
 * `deployment-operations`: *"Every deployed service SHALL expose two separate
 * signals"*, and the liveness one *"SHALL NOT perform input or output against
 * any dependency"*. So this handler reads nothing, calls nothing and answers
 * because the process is up. It is the only signal Coolify may restart a
 * container over; `/readyz` is what the routing gate reads, and conflating the
 * two is how an instance that is merely warming up gets killed instead of
 * waited for.
 */
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { ALIVE } from '$lib/readiness';

export const prerender = false;

export const GET: RequestHandler = () => json({ status: ALIVE });
