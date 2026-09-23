/**
 * The asset browser — the first screen where a human, rather than an agent,
 * answers *"where is the mech scout"*.
 *
 * Everything in here is a pure decision over what the surface answered, so the
 * whole of group 4 is testable without a browser and without SvelteKit: the
 * route's `load` calls :func:`browserScreen`, and the components render the
 * :type:`BrowserView` it produces.
 */

export * from './disclosure';
export * from './results';
export * from './screens';
export * from './degradation';
export * from './semantic';
export * from './load';
