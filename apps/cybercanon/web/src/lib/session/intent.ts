/**
 * Where the person was going before they were asked to sign in.
 *
 * `web-session` requires that *"after signing in, the person SHALL be taken to
 * the address they originally requested, not to a default landing screen"* —
 * which is the difference between a link pasted into Discord working and a link
 * pasted into Discord dumping eight people on a project picker.
 *
 * The intended address travels **in the address** (D3), as `?next=` on the
 * sign-in screen, for the same reason everything else does: a reload, a second
 * tab or a browser that discarded the page cannot desynchronise a URL from
 * itself. Nothing about it is remembered anywhere else.
 *
 * `next` is attacker-supplied by construction — anybody can send a link to
 * `/sign-in?next=…` — so it is validated as a same-application path before it
 * is ever navigated to. A scheme, an authority or a protocol-relative `//host`
 * is discarded in favour of the root, which turns the open redirect into a
 * boring landing.
 */

export const SIGN_IN_PATH = '/sign-in';
export const SIGNED_IN_PATH = '/signed-in';
export const NEXT_PARAMETER = 'next';
export const HOME = '/';

/** The sign-in address that comes back here afterwards. */
export function signInAddress(intended: string): string {
	const target = localAddress(intended);
	if (target === HOME) return SIGN_IN_PATH;
	return `${SIGN_IN_PATH}?${NEXT_PARAMETER}=${encodeURIComponent(target)}`;
}

/** The address a sign-in screen was asked to return to, defaulted and checked. */
export function intendedAddress(url: URL): string {
	return localAddress(url.searchParams.get(NEXT_PARAMETER));
}

/**
 * This application's own address, or the root.
 *
 * A single leading slash and no second one: `/p/x/a/y` passes, `//evil.example`
 * and `https://evil.example` do not, and neither does anything a browser would
 * resolve against another origin.
 */
export function localAddress(candidate: string | null | undefined): string {
	if (!candidate || !candidate.startsWith('/') || candidate.startsWith('//')) return HOME;
	if (candidate.includes('\\') || /^\/+[a-z][a-z0-9+.-]*:/i.test(candidate)) return HOME;
	return candidate;
}

/** The address a page is at, as this application addresses it — path and query. */
export function currentAddress(url: URL): string {
	return `${url.pathname}${url.search}`;
}
