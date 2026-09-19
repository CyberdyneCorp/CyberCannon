/**
 * D4 — the one place the application reaches the Cyberdyne design system.
 *
 * Every screen imports its primitives from here, so "does this application use
 * the design system" is a question with one answer and one file, and adding a
 * primitive is a line here rather than a component somewhere.
 *
 * **The two packages are not installed in this checkout.** They are published to
 * GitHub Packages and need a credential this repository does not carry; task
 * 1.2 of `add-web-app-shell` is what installs them, and until it is done this
 * module re-exports nothing. What is already real is the constraint: the
 * inventory in `design-system.json` names every primitive the library provides,
 * and `tests/tooling/test_web_structure.py` fails the build when a local
 * component reimplements one of them. That test does not depend on the packages
 * being installable, which is deliberate — the rule that matters is the one that
 * bites before the first local Button is written, not after.
 *
 * When 1.2 lands, this module becomes:
 *
 * ```ts
 * export { Button, Card, Field, Input, Select } from '@cyberdynecorp/svelte-ui-core';
 * import '@cyberdynecorp/svelte-ui-foundation/styles.css';
 * ```
 *
 * and nothing else in the application changes, because nothing else ever named
 * the package.
 */

import inventory from '../../design-system.json';

/** The package the primitives come from. */
export const DESIGN_SYSTEM = inventory.package;

/** The foundation package whose styles the frame loads. */
export const DESIGN_FOUNDATION = inventory.foundation;

/** Every primitive the library provides, and therefore every one not to write. */
export const PRIMITIVES: readonly string[] = inventory.primitives;

/** Whether the library is installed in this checkout (task 1.2). */
export const INSTALLED = inventory.verified_against !== null;
