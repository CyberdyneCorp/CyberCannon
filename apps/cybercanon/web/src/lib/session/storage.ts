/**
 * Where a credential is kept between two page loads, and why it is not kept long.
 *
 * `sessionStorage` rather than `localStorage`: a closed tab ends the session,
 * which is the behaviour a person sharing a machine in a studio expects and the
 * cheapest half of *"a subsequent person using the same browser sees nothing of
 * the previous session"*. The other half is the query cache, which sign-out
 * clears (`web-session`, D2).
 *
 * Every access is wrapped, because a browser with site data blocked throws on
 * the property itself rather than on the call — and a frame that cannot render
 * because storage is disabled is a worse failure than a session that does not
 * survive a reload.
 */

export interface SessionStorage {
	read(key: string): string | null;
	write(key: string, value: string): void;
	remove(key: string): void;
}

/** What tests use, and what a browser that refuses storage degrades to. */
export function memoryStorage(): SessionStorage {
	const held = new Map<string, string>();
	return {
		read: (key) => held.get(key) ?? null,
		write: (key, value) => void held.set(key, value),
		remove: (key) => void held.delete(key)
	};
}

/**
 * One in-memory stand-in, shared.
 *
 * Deliberately module-level rather than one per call: a sign-in writes its
 * proof key and the return reads it, and two callers handed two different empty
 * maps would be a sign-in that silently never completes. A browser with site
 * data blocked is exactly that case, and it has to work.
 */
const FALLBACK = memoryStorage();

/** The tab's own storage, or an in-memory stand-in when there is none. */
export function browserStorage(): SessionStorage {
	const backing = available();
	if (!backing) return FALLBACK;
	return {
		read: (key) => guard(() => backing.getItem(key), null),
		write: (key, value) => guard(() => backing.setItem(key, value), undefined),
		remove: (key) => guard(() => backing.removeItem(key), undefined)
	};
}

function available(): Storage | null {
	return guard(() => globalThis.sessionStorage ?? null, null);
}

function guard<T>(read: () => T, fallback: T): T {
	try {
		return read();
	} catch {
		return fallback;
	}
}
