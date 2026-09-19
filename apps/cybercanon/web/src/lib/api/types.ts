/**
 * The shapes the `http-api` surface renders, as types.
 *
 * Every field here is one `libs/cybercanon/adapters/inbound/http/payloads.py`
 * writes, spelled the same way. Within a version the surface only *adds*, so a
 * field this file does not know about is ignored rather than rejected — which
 * is what lets the backend ship an optional field without breaking a client
 * written against the version before it.
 */

export const SURFACE_VERSION = 'v1';

/** The six outcomes the domain can express. There is no seventh. */
export const FAILURE_KINDS = [
	'not_found',
	'forbidden',
	'unauthenticated',
	'invalid',
	'conflict',
	'unavailable'
] as const;
export type FailureKind = (typeof FAILURE_KINDS)[number];

/** What a read states about the revision it was served from (`hosted-repository`). */
export interface Freshness {
	readonly revision: string;
	readonly confirmedAt: string;
	readonly mayBeStale: boolean;
}

export interface Failure {
	readonly kind: FailureKind;
	readonly identifier: string;
	readonly message: string;
	readonly subject: string | null;
	readonly correlationId: string | null;
}

export type ApiResult<T> =
	| { readonly ok: true; readonly data: T; readonly freshness: Freshness | null }
	| { readonly ok: false; readonly failure: Failure };

export interface Page<T> {
	readonly items: readonly T[];
	readonly next_token: string | null;
	readonly page_size: number;
	readonly total: number;
}

export interface Owner {
	readonly discipline: string;
	readonly display: string;
	readonly recorded: boolean;
	readonly unmapped: boolean;
}

export interface AssetRow {
	readonly asset: string;
	readonly name: string;
	readonly status: string;
	readonly owners: readonly Owner[];
}

export interface Location {
	readonly label: string;
	readonly value: string;
	readonly recorded: boolean;
}

export interface LocationAnswer {
	readonly asset: string;
	readonly name: string;
	readonly status: string;
	readonly project: string;
	readonly locations: readonly Location[];
	readonly owners: readonly Owner[];
	readonly stale: boolean;
	readonly notice: string;
}

/** One search result, and the pass of the cascade that found it (`asset-lookup`). */
export interface SearchHit {
	readonly asset: string;
	readonly name: string;
	readonly matched: string;
}

export interface LensedSpec {
	readonly asset: string;
	readonly source: string;
	readonly lens: string | null;
	readonly body: string;
	readonly full: string;
	readonly notice: string;
}

export interface CompiledSpec {
	readonly asset: string;
	readonly source: string;
	readonly text: string;
}

export interface ProjectBriefing {
	readonly project: string;
	readonly text: string;
}

export interface Violation {
	readonly rule_id: string;
	readonly severity: string;
	readonly subject: string;
	readonly observed: string;
	readonly expected: string;
	readonly message: string;
}

export interface NotEvaluated {
	readonly rule_id: string;
	readonly missing_fact: string;
	readonly reason: string;
}

export interface Report {
	readonly asset: string;
	readonly export: string;
	readonly export_format: string;
	readonly outcome: string;
	readonly violations: readonly Violation[];
	readonly not_evaluated: readonly NotEvaluated[];
	readonly passed_rules: readonly string[];
}

export type ValidationOutcome = Report & {
	readonly spec: string;
	readonly passed: boolean;
	readonly spec_warnings: readonly Violation[];
};

export interface RequestEvent {
	readonly kind: string;
	readonly actor: string;
	readonly at: string;
	readonly state: string | null;
	readonly assignee: string | null;
	readonly reason: string;
}

export interface AssetRequest {
	readonly id: string;
	readonly author: string;
	readonly discipline: string;
	readonly description: string;
	readonly asset: string | null;
	readonly asked_for: string | null;
	readonly assignee: string | null;
	readonly state: string;
	readonly terminal: boolean;
	readonly needs_owner: boolean;
	readonly history: readonly RequestEvent[];
}

export interface RecordedRequest {
	readonly request: AssetRequest;
	readonly revision: string;
}

export interface RequestListing {
	readonly project: string;
	readonly requests: readonly AssetRequest[];
	readonly unreadable: readonly { readonly path: string; readonly reason: string }[];
}

export interface UnreadItems {
	readonly project: string;
	readonly actor: string;
	readonly count: number;
	readonly items: readonly AssetRequest[];
}

export interface Dismissal {
	readonly project: string;
	readonly actor: string;
	readonly request: string;
	readonly at: string;
}

export interface WriteOutcome {
	readonly project: string;
	readonly revision: string;
	readonly paths: readonly string[];
	readonly author: string;
	readonly message: string;
	readonly attempts: number;
}
