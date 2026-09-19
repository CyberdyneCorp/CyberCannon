/**
 * What the web application's readiness answers, as one word in one place.
 *
 * The endpoint is process-only (D10), so this module is deliberately the whole
 * of what it depends on: a constant. Anything else importable from a readiness
 * route is something that could one day make readiness reach for the API.
 */
export const READY = 'ready';
