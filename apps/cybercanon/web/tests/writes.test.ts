/**
 * Tasks 3.3 and 3.4 — D5, which is the decision this whole change is judged on.
 *
 * *"Losing someone's writing once is enough for them to stop using the tool"*,
 * so both branches of the scenario are executed and both are asserted for what
 * they must **not** do as much as for what they do:
 *
 * * the successful path replays the original request **under its original
 *   idempotency key**, with the payload untouched — the person retypes nothing,
 *   and a write that had in fact landed before the credential was refused comes
 *   back as its own replay rather than as a second annotation (`http-api`);
 * * the declined path sends nothing at all. Not a retry, not a "save draft"
 *   call, nothing — and the payload comes back so the screen keeps showing it.
 *
 * The counter on the stand-in surface is what makes those claims checkable: it
 * counts sends and records the key each one carried, which is the only way to
 * tell a replay from a duplicate.
 */

import { describe, expect, it } from 'vitest';
import type { ApiResult } from '../src/lib/api/types';
import { SessionStore } from '../src/lib/session/session';
import { memoryStorage } from '../src/lib/session/storage';
import {
	EXPIRED_MESSAGE,
	KEPT_MESSAGE,
	WriteGate,
	heldWrite,
	newIdempotencyKey
} from '../src/lib/session/writes';
import { mappedPerson } from './support/credentials';

const ANNOTATION = {
	asset: 'mech_scout',
	body: 'The left pauldron reads as plastic under the rim light. Matte it down.'
};

function session(): SessionStore {
	return new SessionStore({ storage: memoryStorage() });
}

const REFUSED: ApiResult<never> = {
	ok: false,
	failure: {
		kind: 'unauthenticated',
		identifier: 'auth.expired',
		message: 'the credential has expired',
		subject: null,
		correlationId: null
	}
};

const FORBIDDEN: ApiResult<never> = {
	ok: false,
	failure: {
		kind: 'forbidden',
		identifier: 'policy.refused',
		message: 'promotion is reserved to the art director',
		subject: null,
		correlationId: null
	}
};

/**
 * A surface that refuses until a credential arrives, and remembers everything.
 *
 * `accepted` is what the API would have recorded, so a test can assert that one
 * write reached it once rather than that a function was called twice.
 */
function surface(answers: ApiResult<{ revision: string }>[]) {
	const keys: string[] = [];
	const payloads: unknown[] = [];
	let answered = 0;
	const send = (payload: unknown) => async (key: string) => {
		keys.push(key);
		payloads.push(payload);
		return answers[Math.min(answered++, answers.length - 1)];
	};
	return { keys, payloads, send, get sends() {
		return keys.length;
	} };
}

const ACCEPTED: ApiResult<{ revision: string }> = {
	ok: true,
	data: { revision: 'a1b2c3' },
	freshness: null
};

describe('a session that expires while somebody is writing', () => {
	it('holds the request instead of losing it', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED]);
		const write = heldWrite({
			describe: 'Your annotation on mech_scout',
			payload: ANNOTATION,
			send: api.send(ANNOTATION)
		});

		const submission = await gate.submit(write);

		expect(submission).toMatchObject({ kind: 'held', message: EXPIRED_MESSAGE });
		expect(gate.held()).toBe(write);
		expect(gate.held()?.payload).toEqual(ANNOTATION);
	});

	it('moves the session to expired, keeping who it belonged to', async () => {
		const store = session();
		store.signIn(mappedPerson());
		const gate = new WriteGate(store);
		const api = surface([REFUSED]);

		await gate.submit(heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) }));

		expect(store.current().kind).toBe('expired');
		expect(store.identity()?.display).toBe('Rafa');
	});

	it('submits it afterwards with that text, and the person retypes nothing', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED, ACCEPTED]);
		const write = heldWrite({
			describe: 'Your annotation on mech_scout',
			payload: ANNOTATION,
			send: api.send(ANNOTATION)
		});
		await gate.submit(write);

		const replayed = await gate.replay();

		expect(replayed).toMatchObject({ kind: 'completed', result: ACCEPTED });
		expect(api.payloads).toEqual([ANNOTATION, ANNOTATION]);
		expect(gate.held()).toBeNull();
	});

	it('replays it under the key it was first sent with, so a landed write is not doubled', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED, ACCEPTED]);
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) });
		await gate.submit(write);

		await gate.replay();

		expect(api.sends).toBe(2);
		expect(api.keys[0]).toBe(write.key);
		expect(api.keys[1]).toBe(write.key);
	});

	it('holds it again if the second credential is refused too', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED]);
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) });
		await gate.submit(write);

		const again = await gate.replay();

		expect(again).toMatchObject({ kind: 'held' });
		expect(gate.held()?.payload).toEqual(ANNOTATION);
	});

	it('replays nothing when nothing was held', async () => {
		expect(await new WriteGate(session()).replay()).toBeNull();
	});
});

describe('declining to re-authenticate', () => {
	it('leaves the input unsubmitted', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED, ACCEPTED]);
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) });
		await gate.submit(write);

		gate.decline();

		expect(api.sends).toBe(1);
	});

	it('hands the text back, so it stays on screen and recoverable', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED]);
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) });
		await gate.submit(write);

		const kept = gate.decline();

		expect(kept).toMatchObject({ kind: 'kept', message: KEPT_MESSAGE });
		expect(kept?.write.payload).toEqual(ANNOTATION);
		expect(kept?.write.key).toBe(write.key);
	});

	it('leaves the same write submittable later, under the same key', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED, ACCEPTED]);
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) });
		await gate.submit(write);
		const kept = gate.decline();

		const later = await gate.submit(kept!.write);

		expect(later).toMatchObject({ kind: 'completed' });
		expect(api.keys).toEqual([write.key, write.key]);
	});

	it('declines nothing when nothing was held', () => {
		expect(new WriteGate(session()).decline()).toBeNull();
	});
});

describe('what the gate does not hold', () => {
	it('is a write the surface answered', async () => {
		const gate = new WriteGate(session());
		const api = surface([ACCEPTED]);

		const submission = await gate.submit(
			heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) })
		);

		expect(submission).toMatchObject({ kind: 'completed' });
		expect(gate.held()).toBeNull();
	});

	it('is a refusal that has nothing to do with the credential', async () => {
		const gate = new WriteGate(session());
		const api = surface([FORBIDDEN]);

		const submission = await gate.submit(
			heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) })
		);

		expect(submission).toMatchObject({ kind: 'completed', result: FORBIDDEN });
		expect(gate.held()).toBeNull();
	});

	it('is anything at all once the person signs out', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED]);
		await gate.submit(heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) }));

		gate.discard();

		expect(gate.held()).toBeNull();
	});
});

describe('the idempotency key', () => {
	it('is generated once, when the draft becomes a write', () => {
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: async () => ACCEPTED });

		expect(write.key).toBeTruthy();
		expect(write.key).toBe(write.key);
	});

	it('is different for two different drafts', () => {
		expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
	});

	it('is the one given, when a screen is restoring a draft it already keyed', () => {
		const write = heldWrite({
			key: 'key-from-the-draft',
			describe: 'x',
			payload: ANNOTATION,
			send: async () => ACCEPTED
		});

		expect(write.key).toBe('key-from-the-draft');
	});
});

describe('watchers of the gate', () => {
	it('are told what is waiting and when nothing is', async () => {
		const gate = new WriteGate(session());
		const api = surface([REFUSED]);
		const seen: (string | null)[] = [];
		gate.subscribe((held) => seen.push(held ? held.key : null));
		const write = heldWrite({ describe: 'x', payload: ANNOTATION, send: api.send(ANNOTATION) });

		await gate.submit(write);
		gate.decline();

		expect(seen).toEqual([null, write.key, null]);
	});
});
