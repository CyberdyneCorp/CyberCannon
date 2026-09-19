/**
 * D2 — server state lives in one query cache, never in a ViewModel or a component.
 *
 * The alternative is the same asset's status held by three components that
 * disagree after a promotion. Putting it in the `AnnotationViewModel` would be
 * worse: it would make the ViewModel untestable without a network, which was
 * the entire reason for having one.
 *
 * The cache is deliberately small. It remembers an answer per resource key, it
 * de-duplicates concurrent loads of the same key, and it forgets what a write
 * says to forget. It has no stale-while-revalidate policy, no background
 * refetch and no time-to-live, because `hosted-repository` already makes every
 * read state the revision it was served from — freshness is a fact the surface
 * reports, not one the client guesses.
 */

import type { ResourceKey } from './resources';
import { isUnder } from './resources';

export interface Entry<T> {
	readonly value: T;
	readonly at: number;
}

export type Loader<T> = () => Promise<T>;

export class QueryCache {
	readonly #entries = new Map<ResourceKey, Entry<unknown>>();
	readonly #inFlight = new Map<ResourceKey, Promise<unknown>>();
	readonly #now: () => number;

	constructor(now: () => number = () => Date.now()) {
		this.#now = now;
	}

	/** What is remembered for this key, or `undefined` — never a guess. */
	peek<T>(key: ResourceKey): T | undefined {
		return this.#entries.get(key)?.value as T | undefined;
	}

	has(key: ResourceKey): boolean {
		return this.#entries.has(key);
	}

	keys(): readonly ResourceKey[] {
		return [...this.#entries.keys()];
	}

	set<T>(key: ResourceKey, value: T): void {
		this.#entries.set(key, { value, at: this.#now() });
	}

	/**
	 * The cached answer, or one load of it.
	 *
	 * Two screens mounting at once ask once: the in-flight promise is shared,
	 * which is what keeps "the browser and the header both want this project's
	 * assets" from being two requests that can disagree.
	 */
	async read<T>(key: ResourceKey, load: Loader<T>): Promise<T> {
		const remembered = this.#entries.get(key);
		if (remembered) return remembered.value as T;
		const running = this.#inFlight.get(key);
		if (running) return running as Promise<T>;
		const started = load()
			.then((value) => {
				this.set(key, value);
				return value;
			})
			.finally(() => this.#inFlight.delete(key));
		this.#inFlight.set(key, started);
		return started;
	}

	/** Forget every key at or under these prefixes. Returns what was forgotten. */
	invalidate(prefixes: readonly ResourceKey[]): readonly ResourceKey[] {
		const dropped = this.keys().filter((key) => prefixes.some((prefix) => isUnder(key, prefix)));
		for (const key of dropped) this.#entries.delete(key);
		return dropped;
	}

	/** Everything, forgotten — what signing out does (`web-session`). */
	clear(): void {
		this.#entries.clear();
		this.#inFlight.clear();
	}
}

/** The one cache. A second instance is a second copy of the truth. */
export const queryCache = new QueryCache();
