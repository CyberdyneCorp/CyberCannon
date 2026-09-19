<script lang="ts">
	import RouteScreen from '$lib/components/RouteScreen.svelte';
	import AssetSurface from '$lib/components/AssetSurface.svelte';
	import type { LensedSpec } from '$lib/api';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<h1>{data.address.asset}</h1>

<RouteScreen state={data.state}>
	{#snippet content(spec: LensedSpec)}
		<AssetSurface surface={data.address.surface} asset={spec} />
	{/snippet}
</RouteScreen>
