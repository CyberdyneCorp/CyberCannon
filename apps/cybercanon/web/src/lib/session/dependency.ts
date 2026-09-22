/**
 * What the frame's data depends on besides the address: who is signed in.
 *
 * SvelteKit re-runs a load when a parameter it used changed or when something
 * it depends on is invalidated, and the frame's load uses no parameter — so
 * without this, the projects read for an anonymous visitor would still be on
 * screen after they signed in. The frame invalidates it when the acting
 * identity changes, which covers signing in, signing out and an in-place
 * re-authentication (D5) without any of the three knowing about the other two.
 *
 * **It lives here rather than in `+layout.ts` because a route module may only
 * export what SvelteKit names.** `load`, `prerender`, `csr`, `ssr`,
 * `trailingSlash`, `config`, `entries` — anything else is rejected, and the
 * rejection is a runtime error that replaces the whole application with
 * *"500 Internal Error"* in `just web` and in any development build. A constant
 * two modules share is an ordinary module, and this is it.
 */
export const SESSION_DEPENDENCY = 'canon:session';
