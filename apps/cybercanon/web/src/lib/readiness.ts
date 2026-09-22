/**
 * What the web application's two signals answer, as two words in one place.
 *
 * Both endpoints are process-only (D10), so this module is deliberately the
 * whole of what they depend on: two constants. Anything else importable from a
 * liveness or readiness route is something that could one day make a health
 * signal reach for the API — and `deployment-operations` requires the liveness
 * one to perform *"no input or output against any dependency"* at all.
 */
export const READY = 'ready';

export const ALIVE = 'alive';
