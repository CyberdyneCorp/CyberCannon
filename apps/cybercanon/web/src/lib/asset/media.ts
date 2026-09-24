/** One physical concept view may have both a declared path and a slot name. */
export interface SheetViewGroup {
	readonly slot: string;
	readonly aliases: readonly string[];
}

export interface SheetImage {
	readonly source: string | null;
	readonly reason: string | null;
}

const SLOT = /^[a-z0-9][a-z0-9_]{0,31}$/;
const IMAGE_PATH = /^(?:concept\/)?([a-z0-9][a-z0-9_]{0,31})\.(?:png|jpe?g|webp|tiff)$/;

export function canonicalView(name: string): string {
	return IMAGE_PATH.exec(name)?.[1] ?? name;
}

export function sheetViews(names: readonly string[]): readonly SheetViewGroup[] {
	const groups = new Map<string, string[]>();
	for (const name of names) {
		const slot = canonicalView(name);
		groups.set(slot, [...(groups.get(slot) ?? []), name]);
	}
	return [...groups].map(([slot, aliases]) => ({ slot, aliases }));
}

export function isViewSlot(name: string): boolean {
	return SLOT.test(name);
}

export function imageType(path: string): string | null {
	const extension = path.split('.').at(-1)?.toLowerCase();
	switch (extension) {
		case 'png': return 'image/png';
		case 'jpg':
		case 'jpeg': return 'image/jpeg';
		case 'webp': return 'image/webp';
		case 'tiff': return 'image/tiff';
		default: return null;
	}
}
