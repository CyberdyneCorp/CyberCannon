/**
 * What the two sign-in screens say, and the identifier a refusal carries.
 *
 * They live here rather than in the route modules that use them because **a
 * route module may only export what SvelteKit names** — `load`, `prerender`,
 * `csr`, `ssr`, `trailingSlash`, `config`, `entries`, or a `_`-prefixed name.
 * Anything else is refused at run time and the refusal replaces the whole
 * application with an error, which is not caught by a production build and is
 * exactly what `just web` serves. A constant two modules share is an ordinary
 * module, and `tests/tooling/test_web_structure.py` keeps it that way.
 */

/** What a deployment with no identity service configured tells a visitor. */
export const NOT_CONFIGURED =
	'This deployment has no identity service configured, so nobody can sign in ' +
	'here yet. Everything else about the application is working.';

/** What is unavailable when it is not configured — named, never implied. */
export const SIGN_IN = 'Sign-in';

/** The identifier a refused exchange is reported under (`web-session`). */
export const REFUSED = 'sign-in.refused';
