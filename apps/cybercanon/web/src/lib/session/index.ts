/**
 * The session experience, in one place: who is acting, how they arrive, what
 * happens to their work when a credential lapses, and what leaves with them.
 *
 * Nothing here is a ViewModel (D1) and nothing here holds server state (D2).
 * The store holds a credential and an identity; the gate holds at most one
 * unsent write; the query cache holds everything that came from the surface,
 * and sign-out empties it.
 */

export * from './guard';
export * from './identity';
export * from './intent';
export * from './oidc';
export * from './reauthentication';
export * from './session';
export * from './storage';
export * from './verification';
export * from './writes';

import { sessionStore } from './session';
import { WriteGate } from './writes';

/**
 * The one gate every write goes through.
 *
 * It is paired with the one session, because holding a write is only meaningful
 * against the session that expired underneath it — two gates would be two
 * answers to *"is there something waiting to be re-sent"*, which is the
 * question the prompt on screen is asking.
 */
export const writeGate = new WriteGate(sessionStore);
