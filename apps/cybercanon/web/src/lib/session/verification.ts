/**
 * An identity provider outage degrades the session; it does not blank the screen.
 *
 * `web-session` is specific about what must keep working: *"when the identity
 * provider is unreachable but the person's session remains valid, the
 * application SHALL continue to serve reads and SHALL state that actions
 * requiring re-verification are temporarily unavailable"*.
 *
 * Both halves fall out of decisions already taken elsewhere, which is why this
 * module is small:
 *
 * * **reads continue** because the credential the application already holds is
 *   verified by the API against keys it has cached — `auth-integration`
 *   requires key rotation to be tolerated *"without a restart"* — and because
 *   `deployment-operations` classifies the identity service as `OPTIONAL`, so
 *   it never withholds readiness. Nothing in a read path asks the issuer
 *   anything. The degradation is therefore something to **say**, not something
 *   to implement: the honest failure would be an application that invented an
 *   outage of its own and stopped rendering.
 * * **what is unavailable is naming itself**: the API's open readiness answer
 *   lists its degraded dependencies, and `identity_service` is one of the names
 *   `service_health.py` fixes so *"two deployments agree on them"*.
 *
 * So this reads a signal the surface already publishes and turns it into one
 * sentence. It never decides that the provider is down on its own evidence.
 */

/** The dependency name the API reports. It matches `service_health.IDENTITY_SERVICE`. */
export const IDENTITY_SERVICE = 'identity_service';

export const VERIFICATION_UNAVAILABLE =
	'The identity service is unreachable. Your session is still valid and reading ' +
	'continues to work; signing in, signing out and re-authenticating are ' +
	'temporarily unavailable.';

/** What the readiness answer said about its dependencies, as far as this matters. */
export interface Degradation {
	readonly degraded?: readonly string[];
}

/** Whether the identity provider is among the dependencies the API reports down. */
export function identityProviderDown(reported: Degradation | null | undefined): boolean {
	return Boolean(reported?.degraded?.includes(IDENTITY_SERVICE));
}

/**
 * The notice the frame shows, or `null` when there is nothing to say.
 *
 * One sentence rather than a state: an outage of somebody else's service is not
 * a member of the closed route-state set (D6), because the route resolved
 * perfectly well. It is a disclosure beside content that is entirely correct.
 */
export function verificationNotice(reported: Degradation | null | undefined): string | null {
	return identityProviderDown(reported) ? VERIFICATION_UNAVAILABLE : null;
}

/** The degraded names an `/readyz` body carries, read defensively. */
export function degradationOf(body: unknown): Degradation {
	const reported = (body ?? {}) as { degraded?: unknown };
	const names = Array.isArray(reported.degraded) ? reported.degraded : [];
	return { degraded: names.filter((name): name is string => typeof name === 'string') };
}
