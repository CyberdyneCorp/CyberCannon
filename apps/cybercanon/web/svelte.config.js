import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
export default {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		// D3 — the address is the state. Trailing slashes would give one screen
		// two addresses, and a link is only shareable if there is one of it.
		alias: { $api: 'src/lib/api' }
	}
};
