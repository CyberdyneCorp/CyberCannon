/**
 * Task 2.4 — the API's outcome vocabulary, translated once into route states.
 *
 * `http-api` maps each of the six outcomes the domain can express to exactly
 * one status class, *"through one mapping used by every endpoint"*. This is the
 * other end of that seam, and it is one mapping for the same reason: a screen
 * that decided for itself what a 409 meant would be the fourth screen that
 * decided slightly differently.
 *
 * The closed route-state set (D6) has six members and so does the failure
 * vocabulary, but they are not the same six and the translation is not an
 * identity:
 *
 * * **unauthenticated** is not an error screen. `web-session` requires a person
 *   arriving without a session to be *offered sign-in* — so it becomes a
 *   `forbidden` state carrying the `sign-in` remedy, which is what lets D5's
 *   in-place re-authentication be offered rather than a redirect performed.
 * * **unavailable** is `degraded`, not `failed`: *"a precondition outside the
 *   caller's control is unmet — for now"* is the rebuilding index and the
 *   unreachable delegated search that `asset-browser` requires be disclosed
 *   beside whatever could still be served.
 * * **invalid** and **conflict** are `failed`: the request as sent cannot be
 *   completed, and the identifier says which one it was so a write path can
 *   offer the retry `http-api`'s idempotency rules make safe.
 */

import type { Failure, FailureKind } from './types';
import { FAILURE_KINDS } from './types';
import type { RouteState } from '../route-state';
import { degraded, failed, forbidden, notFound } from '../route-state';

/** The status classes `http-api` answers with, read back into the vocabulary. */
export const KIND_BY_STATUS: Readonly<Record<number, FailureKind>> = {
	400: 'invalid',
	401: 'unauthenticated',
	403: 'forbidden',
	404: 'not_found',
	409: 'conflict',
	503: 'unavailable'
};

/** The identifier an unexpected failure carries — the one the domain did not express. */
export const INTERNAL_IDENTIFIER = 'internal.failure';

export function isFailureKind(value: string): value is FailureKind {
	return (FAILURE_KINDS as readonly string[]).includes(value);
}

/**
 * The kind a status code names.
 *
 * Anything outside the mapping — a 500, a proxy's 502, a gateway timeout — is
 * `unavailable` rather than invented, because the one thing a client must not
 * do is report a failure the domain did not express as though it had.
 */
export function kindForStatus(status: number): FailureKind {
	return KIND_BY_STATUS[status] ?? 'unavailable';
}

/** One failure as the screen it produces. The whole of this seam's translation. */
export function routeStateFor<T>(failure: Failure): RouteState<T> {
	switch (failure.kind) {
		case 'not_found':
			return notFound(failure.message, failure.subject);
		case 'forbidden':
			return forbidden(failure.message, 'none');
		case 'unauthenticated':
			return forbidden(failure.message, 'sign-in');
		case 'unavailable':
			return degraded<T>(null, [failure.subject ?? failure.identifier], failure.message);
		case 'invalid':
		case 'conflict':
			return failed(failure.identifier, failure.message, failure.correlationId);
	}
}
