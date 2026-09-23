#!/usr/bin/env node
/**
 * The design-system adherence gate.
 *
 * `openspec/project.md` ("Visual language — neo-brutalism") makes this
 * mechanical rather than a review habit: *"Tokens live in exactly one file. A
 * component that writes a hex value, a font stack, a border width or a shadow
 * offset inline is a bug, and the check is mechanical rather than a review
 * habit."* That is the repointed D4, and it is the one rule whose violation is
 * invisible later — a hex that slips in looks right on the day and is
 * unfindable the day the ground colour changes.
 *
 * The rules are Broadsheet's own, from `_adherence.oxlintrc.json`: raw hex,
 * raw lengths where a token exists, and off-system fonts. They are reimplemented
 * rather than run, because that file lints React JSX with oxlint and this
 * application is Svelte with scoped `<style>` blocks — the violations live in
 * CSS text the JavaScript linter never parses.
 *
 * WHAT IS SCANNED
 *   src/ **.svelte   — the `<style>` block only; markup and script are not CSS
 *   src/ **.ts       — the whole file, comments stripped
 *   src/ **.css      — except the token layer itself, which is where the
 *                      literals are supposed to be
 *
 * THE RULES
 *   color / font / border / radius / shadow — a literal where a token exists.
 *   token — a `var(--…)` that names nothing. That is the quietest failure CSS
 *     has: the declaration is dropped and the element keeps whatever it had, so
 *     a typo, or a ramp step the design never defined, reads as a style that
 *     simply did not take. Same invisible-later mistake as a raw hex, so the
 *     same kind of build failure.
 *
 * THE WAIVER LIST
 *   `adherence.json` names the components still awaiting the restyle: they are
 *   reported and do not fail the build. A listed file that has gone clean DOES
 *   fail it, so the list can only shrink. See that file's own comment.
 *
 * WHAT IS NOT SCANNED, AND WHY
 *   Spacing. The scale has six steps (5/10/15/20/30/40px) and the design's own
 *   page gutters are not on it, so a spacing gate would fail the design it is
 *   meant to enforce. Colour, font, border width, radius and shadow are the
 *   five the system actually carries a token for, and they are the five here.
 *
 * Usage:  node scripts/adherence.mjs [root]      (root defaults to this app)
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SCANNED = new Set(['.svelte', '.ts', '.css']);
const SKIPPED_DIRS = new Set(['node_modules', '.svelte-kit', 'build', 'static']);

/** Where the literals belong: the token layer, and the generated font faces. */
const TOKEN_LAYER = ['src/lib/styles/tokens.css', 'src/lib/styles/fonts.css'];

/** The vocabulary itself — the file every `var(--…)` in the application means. */
const TOKEN_FILE = 'src/lib/styles/tokens.css';

const HEX = /#[0-9a-fA-F]{3,8}\b/g;
const COLOR_FUNCTION = /\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\s*\(/g;
const DECLARATION = /([-a-zA-Z]+)\s*:\s*([^;{}]+)/g;
const LENGTH = /(?<![\w-])\d*\.?\d+(?:px|rem|em|pt|ch|ex)(?![\w-])/;
const BORDER_PROPERTY =
	/^(?:border|outline)(?:-(?:top|right|bottom|left|block|inline|start|end|width))*(?:-width)?$/;
const RADIUS_PROPERTY = /radius$/;
const SHADOW_PROPERTY = /^(?:box|text)-shadow$/;
const VAR_ONLY = /^(?:\s*var\(--[^)]*\)\s*|\s*(?:inherit|initial|unset|revert|none|0)\s*)+$/;
const CUSTOM_PROPERTY = /(--[a-zA-Z0-9-]+)\s*:/g;
const VAR_REFERENCE = /var\(\s*(--[a-zA-Z0-9-]+)/g;

const RULES = {
	color: 'raw colour — every colour comes from a --color-* token via var()',
	font: 'raw font stack — use var(--font-heading), var(--font-body) or var(--font-mono)',
	border: 'raw border width — use var(--border-hairline|thin|thick|heavy)',
	radius: 'raw radius — use var(--radius-sm|md|lg); this system rounds nothing',
	shadow: 'raw shadow — use var(--shadow-sm|md|lg|field|raised|table|pressed)',
	token: 'no such token — src/lib/styles/tokens.css does not declare it, so this'
		+ ' resolves to nothing at all and the declaration is silently dropped'
};

function walk(dir, out = []) {
	for (const entry of readdirSync(dir)) {
		if (SKIPPED_DIRS.has(entry)) continue;
		const path = join(dir, entry);
		if (statSync(path).isDirectory()) walk(path, out);
		else if (SCANNED.has(entry.slice(entry.lastIndexOf('.')))) out.push(path);
	}
	return out;
}

/** Blank out a region so its offsets — and therefore its line numbers — hold. */
function blank(text, start, end) {
	const region = text.slice(start, end).replace(/[^\n]/g, ' ');
	return text.slice(0, start) + region + text.slice(end);
}

/** A `.svelte` file is CSS only inside `<style>`; a `.ts` file is CSS nowhere. */
function scannableText(path, source) {
	if (path.endsWith('.ts')) return stripComments(source);
	if (!path.endsWith('.svelte')) return source;
	let masked = source.replace(/[^\n]/g, ' ');
	for (const match of source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)) {
		const start = match.index + match[0].indexOf('>') + 1;
		masked = masked.slice(0, start) + match[1] + masked.slice(start + match[1].length);
	}
	return stripComments(masked);
}

function stripComments(text) {
	let out = text;
	for (const match of [...out.matchAll(/\/\*[\s\S]*?\*\//g)].reverse()) {
		out = blank(out, match.index, match.index + match[0].length);
	}
	for (const match of [...out.matchAll(/(^|[^:])\/\/[^\n]*/g)].reverse()) {
		out = blank(out, match.index + match[1].length, match.index + match[0].length);
	}
	return out;
}

function lineOf(text, index) {
	let line = 1;
	for (let at = 0; at < index; at += 1) if (text[at] === '\n') line += 1;
	return line;
}

function colourViolations(text) {
	const found = [];
	for (const pattern of [HEX, COLOR_FUNCTION]) {
		pattern.lastIndex = 0;
		for (const match of text.matchAll(pattern)) {
			found.push({ rule: 'color', line: lineOf(text, match.index), snippet: match[0] });
		}
	}
	return found;
}

function ruleFor(property, value) {
	if (property === 'font-family' && !VAR_ONLY.test(value)) return 'font';
	if (VAR_ONLY.test(value)) return null;
	if (SHADOW_PROPERTY.test(property)) return 'shadow';
	if (RADIUS_PROPERTY.test(property)) return value.trim() === '50%' ? null : 'radius';
	if (BORDER_PROPERTY.test(property) && LENGTH.test(value)) return 'border';
	return null;
}

function declarationViolations(text) {
	const found = [];
	DECLARATION.lastIndex = 0;
	for (const match of text.matchAll(DECLARATION)) {
		const property = match[1].toLowerCase();
		if (property.startsWith('--')) continue;
		const rule = ruleFor(property, match[2]);
		if (rule) {
			found.push({
				rule,
				line: lineOf(text, match.index),
				snippet: `${property}: ${match[2].trim()}`
			});
		}
	}
	return found;
}

/**
 * A `var(--…)` that names nothing is the quietest failure CSS has: the
 * declaration is dropped and the element simply keeps whatever it had. It is
 * the same class of invisible-later mistake as a raw hex, so it is the same
 * kind of build failure.
 */
function unresolvedTokens(text, vocabulary) {
	const local = new Set(vocabulary);
	CUSTOM_PROPERTY.lastIndex = 0;
	for (const match of text.matchAll(CUSTOM_PROPERTY)) local.add(match[1]);
	const found = [];
	VAR_REFERENCE.lastIndex = 0;
	for (const match of text.matchAll(VAR_REFERENCE)) {
		if (local.has(match[1])) continue;
		found.push({ rule: 'token', line: lineOf(text, match.index), snippet: `var(${match[1]})` });
	}
	return found;
}

function vocabularyOf(root) {
	const declared = new Set();
	try {
		const text = readFileSync(join(root, TOKEN_FILE), 'utf8');
		CUSTOM_PROPERTY.lastIndex = 0;
		for (const match of text.matchAll(CUSTOM_PROPERTY)) declared.add(match[1]);
	} catch {
		return null;
	}
	return declared;
}

function violationsIn(path, source, vocabulary) {
	const text = scannableText(path, source);
	const found = [
		...colourViolations(text),
		...declarationViolations(text),
		...(vocabulary ? unresolvedTokens(text, vocabulary) : [])
	];
	// A colour literal inside a declaration is reported once, by the colour rule.
	const seen = new Set();
	return found
		.filter((it) => {
			const key = `${it.rule}:${it.line}:${it.snippet}`;
			if (seen.has(key)) return false;
			seen.add(key);
			return true;
		})
		.sort((a, b) => a.line - b.line);
}

function loadPending(root) {
	try {
		const parsed = JSON.parse(readFileSync(join(root, 'adherence.json'), 'utf8'));
		return new Set(parsed.pending ?? []);
	} catch {
		return new Set();
	}
}

function report(entries) {
	for (const { file, found } of entries) {
		for (const it of found) {
			console.error(`  ${file}:${it.line}  [${it.rule}]  ${it.snippet}`);
			console.error(`      ${RULES[it.rule]}`);
		}
	}
}

function main(argv) {
	const here = dirname(fileURLToPath(import.meta.url));
	const root = resolve(argv[2] ?? join(here, '..'));
	const pending = loadPending(root);
	const exempt = new Set(TOKEN_LAYER);
	const vocabulary = vocabularyOf(root);

	const failing = [];
	const waived = [];
	for (const path of walk(join(root, 'src'))) {
		const file = relative(root, path).split(sep).join('/');
		if (exempt.has(file)) continue;
		const found = violationsIn(file, readFileSync(path, 'utf8'), vocabulary);
		if (found.length === 0) continue;
		(pending.has(file) ? waived : failing).push({ file, found });
	}

	const clean = [...pending].filter(
		(file) => !waived.some((it) => it.file === file) && !failing.some((it) => it.file === file)
	);

	if (waived.length > 0) {
		console.error(`design tokens: ${waived.length} file(s) still awaiting the restyle:`);
		for (const { file, found } of waived) console.error(`  ${file} (${found.length})`);
	}

	if (failing.length > 0) {
		console.error('\ndesign tokens: hard-coded values that a token already carries:\n');
		report(failing);
		console.error(
			'\nEvery colour, font, border width, radius and shadow comes from' +
				' src/lib/styles/tokens.css via var(--…). See openspec/project.md,' +
				' "Visual language — neo-brutalism".'
		);
	}

	if (clean.length > 0) {
		console.error(
			'\ndesign tokens: these files are listed in adherence.json as awaiting the' +
				' restyle, but they are clean. Remove them from `pending` — the list is' +
				' only allowed to shrink:\n'
		);
		for (const file of clean) console.error(`  ${file}`);
	}

	if (failing.length > 0 || clean.length > 0) return 1;
	console.log(`design tokens: clean (${waived.length} file(s) pending restyle)`);
	return 0;
}

process.exit(main(process.argv));
