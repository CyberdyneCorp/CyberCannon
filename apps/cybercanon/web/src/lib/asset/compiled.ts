/**
 * Reading the compiled briefing — presentation over one document, nothing else.
 *
 * The asset page shows an asset's effective constraints, its open annotations
 * and its concept views. All three are already *decided* — by
 * `compile_spec`, over the same `EffectiveSpec` the validator enforces — and
 * they arrive in one compiled document. So this module reads that document's
 * sections; it does not merge a project default, resolve a socket, or decide
 * which annotations are open, because every one of those would be a second
 * implementation of something the core owns, and the compiled text and the
 * screen would eventually disagree about what the contract says.
 *
 * The section names are the compiler's own (`briefing.py`), and a heading is
 * matched on the part before its attribution — *"Concept — authored by art"* —
 * so adding a discipline's name to a heading does not silently empty a section.
 * A section the document does not carry reads as absent rather than as an
 * error: `app-navigation` wants absence *stated*, and a thrown parse is not a
 * statement.
 */

/** The headings `briefing.py` writes, before the ` — authored by …` attribution. */
export const CONCEPT = 'Concept';
export const DESIGN = 'Design';
export const CONSTRAINTS = 'Engineering constraints';
export const OPEN_ISSUES = 'Open issues';
export const LINKS = 'Links';

/** What the compiler writes in a section with nothing in it. */
export const NOTHING_DECLARED = '_Nothing declared._';

const HEADING = '## ';
const ATTRIBUTION = ' — ';
const BULLET = '- ';

/** One line of a section: a labelled field, or a sentence that carries its own. */
export interface SectionEntry {
	/** The bold label the compiler wrote, or `null` for a line that has none. */
	readonly label: string | null;
	readonly value: string;
	/** `false` when the value states an absence rather than a recorded fact. */
	readonly recorded: boolean;
	/** A qualifier a screen shows beside the value — an unmapped owner, so far. */
	readonly note?: string;
}

/** Every `##` section of a compiled document, by the name before its attribution. */
export function documentSections(document: string): ReadonlyMap<string, readonly string[]> {
	const sections = new Map<string, string[]>();
	let current: string[] | null = null;
	for (const line of document.split('\n')) {
		if (line.startsWith(HEADING)) {
			current = [];
			sections.set(nameOf(line.slice(HEADING.length)), current);
		} else if (current) {
			current.push(line);
		}
	}
	return sections;
}

/** The body lines of one named section, or none when the document has no such section. */
export function sectionNamed(document: string, name: string): readonly string[] {
	return documentSections(document).get(name) ?? [];
}

/**
 * The entries of a section, with the compiler's own notes and blank lines gone.
 *
 * `_Nothing declared._` produces no entries, which is what makes an empty
 * section indistinguishable from a missing one *to the caller* — and the caller
 * states the absence either way.
 */
export function entriesOf(lines: readonly string[]): readonly SectionEntry[] {
	return lines
		.map((line) => line.trim())
		.filter((line) => line !== '' && !isNote(line))
		.map(entryOf);
}

/** The values of one labelled field, split as the compiler joined them. */
export function valuesLabelled(
	entries: readonly SectionEntry[],
	label: string
): readonly string[] {
	return entries
		.filter((entry) => entry.label === label)
		.flatMap((entry) => entry.value.split(',').map((value) => value.trim()))
		.filter((value) => value !== '');
}

function nameOf(heading: string): string {
	const [name] = heading.split(ATTRIBUTION);
	return name.trim();
}

/** A note or the empty marker: the compiler's italics, never a person's content. */
function isNote(line: string): boolean {
	return line.startsWith('_') && line.endsWith('_');
}

function entryOf(line: string): SectionEntry {
	const body = line.startsWith(BULLET) ? line.slice(BULLET.length) : line;
	const labelled = /^\*\*(?<label>[^*]+)\*\*:\s*(?<value>.*)$/.exec(body);
	if (!labelled?.groups) return { label: null, value: plain(body), recorded: true };
	return {
		label: labelled.groups.label.trim(),
		value: plain(labelled.groups.value),
		recorded: true
	};
}

/** Markdown code fencing removed: the screen has its own way of showing a path. */
function plain(value: string): string {
	return value.trim().replace(/^`(.*)`$/, '$1');
}
