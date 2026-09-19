/**
 * Task 2.1 — the typed client for the `http-api` surface, and the only place
 * this application knows what an HTTP request is.
 *
 * Views never call the API (openspec/project.md); they read the cache, and the
 * cache reads this. The client does exactly three things and decides nothing:
 * it addresses the versioned surface, it carries the credential and the
 * idempotency key in the two headers `http-api` specifies for them, and it
 * turns one response envelope into one :type:`ApiResult`.
 *
 * It never invents a ranking, a filter or a default. `asset-browser` requires
 * search results *"in the order `asset-lookup` specifies"* with no client-side
 * re-sorting, and the cheapest way to keep that true is for the client to have
 * no place to put an opinion.
 */

import {
	SURFACE_VERSION,
	type ApiResult,
	type AssetRow,
	type CompiledSpec,
	type Dismissal,
	type Failure,
	type Freshness,
	type LensedSpec,
	type LocationAnswer,
	type Page,
	type ProjectBriefing,
	type RecordedRequest,
	type RequestListing,
	type SearchHit,
	type UnreadItems,
	type ValidationOutcome,
	type WriteOutcome,
	type AssetRequest
} from './types';
import { INTERNAL_IDENTIFIER, isFailureKind, kindForStatus } from './outcomes';

export const AUTHORIZATION_HEADER = 'Authorization';
export const IDEMPOTENCY_HEADER = 'Idempotency-Key';
export const CORRELATION_HEADER = 'X-Correlation-Id';

export type Fetch = typeof globalThis.fetch;

export interface ClientOptions {
	/** Where the surface is served, without the version segment. */
	readonly baseUrl: string;
	/** SvelteKit hands a route's own `fetch` in; tests hand a fake in. */
	readonly fetch: Fetch;
	/** The session's bearer credential, read at call time so a refresh is seen. */
	readonly token?: () => string | null;
}

export interface ListOptions {
	readonly status?: string;
	readonly owner?: string;
	readonly tag?: string;
	readonly page?: string | null;
	readonly pageSize?: number;
}

export interface WriteOptions {
	/** D11's key: what makes a retry quiet rather than a second write. */
	readonly idempotencyKey?: string;
}

export class CanonClient {
	readonly #baseUrl: string;
	readonly #fetch: Fetch;
	readonly #token: () => string | null;

	constructor(options: ClientOptions) {
		this.#baseUrl = options.baseUrl.replace(/\/+$/, '');
		this.#fetch = options.fetch;
		this.#token = options.token ?? (() => null);
	}

	// ---------------------------------------------------------------- reads

	listAssets(project: string, options: ListOptions = {}): Promise<ApiResult<Page<AssetRow>>> {
		return this.#get(`/projects/${enc(project)}/assets`, listParameters(options));
	}

	readAsset(project: string, asset: string, lens?: string): Promise<ApiResult<LensedSpec>> {
		return this.#get(`/projects/${enc(project)}/assets/${enc(asset)}`, lens ? { lens } : {});
	}

	readBriefing(project: string, asset: string): Promise<ApiResult<CompiledSpec>> {
		return this.#get(`/projects/${enc(project)}/assets/${enc(asset)}/briefing`);
	}

	readLocations(project: string, asset: string): Promise<ApiResult<LocationAnswer>> {
		return this.#get(`/projects/${enc(project)}/assets/${enc(asset)}/locations`);
	}

	search(
		project: string,
		term: string,
		options: Pick<ListOptions, 'page' | 'pageSize'> = {}
	): Promise<ApiResult<Page<SearchHit>>> {
		return this.#get(`/projects/${enc(project)}/search`, { q: term, ...listParameters(options) });
	}

	readProjectBriefing(project: string): Promise<ApiResult<ProjectBriefing>> {
		return this.#get(`/projects/${enc(project)}/briefing`);
	}

	validate(project: string, exportPath: string): Promise<ApiResult<ValidationOutcome>> {
		return this.#get(`/projects/${enc(project)}/validations`, { export: exportPath });
	}

	listRequests(project: string): Promise<ApiResult<RequestListing>> {
		return this.#get(`/projects/${enc(project)}/requests`);
	}

	readRequest(project: string, request: string): Promise<ApiResult<AssetRequest>> {
		return this.#get(`/projects/${enc(project)}/requests/${enc(request)}`);
	}

	readUnread(project: string): Promise<ApiResult<UnreadItems>> {
		return this.#get(`/projects/${enc(project)}/unread`);
	}

	// --------------------------------------------------------------- writes

	writeSpec(
		project: string,
		asset: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<WriteOutcome>> {
		return this.#send('PUT', `/projects/${enc(project)}/assets/${enc(asset)}/spec`, body, options);
	}

	raiseRequest(
		project: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedRequest>> {
		return this.#send('POST', `/projects/${enc(project)}/requests`, body, options);
	}

	assignRequest(
		project: string,
		request: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedRequest>> {
		return this.#send(
			'PUT',
			`/projects/${enc(project)}/requests/${enc(request)}/assignee`,
			body,
			options
		);
	}

	transitionRequest(
		project: string,
		request: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedRequest>> {
		return this.#send(
			'POST',
			`/projects/${enc(project)}/requests/${enc(request)}/transitions`,
			body,
			options
		);
	}

	dismiss(
		project: string,
		request: string,
		options: WriteOptions = {}
	): Promise<ApiResult<Dismissal>> {
		return this.#send(
			'POST',
			`/projects/${enc(project)}/unread/${enc(request)}/dismissal`,
			{},
			options
		);
	}

	// ------------------------------------------------------------ machinery

	#get<T>(path: string, parameters: Record<string, string> = {}): Promise<ApiResult<T>> {
		const search = new URLSearchParams(parameters).toString();
		return this.#request<T>('GET', `${path}${search ? `?${search}` : ''}`, undefined, {});
	}

	#send<T>(
		method: string,
		path: string,
		body: unknown,
		options: WriteOptions
	): Promise<ApiResult<T>> {
		return this.#request<T>(method, path, JSON.stringify(body ?? {}), options);
	}

	async #request<T>(
		method: string,
		path: string,
		body: string | undefined,
		options: WriteOptions
	): Promise<ApiResult<T>> {
		const url = `${this.#baseUrl}/${SURFACE_VERSION}${path}`;
		const response = await this.#fetch(url, {
			method,
			headers: this.#headers(body !== undefined, options),
			body
		});
		return readEnvelope<T>(response, await readJson(response));
	}

	#headers(hasBody: boolean, options: WriteOptions): Record<string, string> {
		const headers: Record<string, string> = { Accept: 'application/json' };
		const token = this.#token();
		if (token) headers[AUTHORIZATION_HEADER] = `Bearer ${token}`;
		if (hasBody) headers['Content-Type'] = 'application/json';
		if (options.idempotencyKey) headers[IDEMPOTENCY_HEADER] = options.idempotencyKey;
		return headers;
	}
}

function enc(segment: string): string {
	return encodeURIComponent(segment);
}

function listParameters(options: ListOptions): Record<string, string> {
	const parameters: Record<string, string> = {};
	if (options.status) parameters.status = options.status;
	if (options.owner) parameters.owner = options.owner;
	if (options.tag) parameters.tag = options.tag;
	if (options.page) parameters.page = options.page;
	if (options.pageSize) parameters.page_size = String(options.pageSize);
	return parameters;
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
	try {
		return (await response.json()) as Record<string, unknown>;
	} catch {
		return {};
	}
}

/**
 * One envelope as one result.
 *
 * A failing response that carries no `error` object is still a failure — a
 * proxy answering 502 with HTML is the ordinary case — so the kind comes from
 * the status and the identifier degrades to the one `http-api` uses for a
 * failure the domain did not express.
 */
export function readEnvelope<T>(
	response: { status: number; ok: boolean; headers: { get(name: string): string | null } },
	body: Record<string, unknown>
): ApiResult<T> {
	const correlationId =
		response.headers.get(CORRELATION_HEADER) ?? asString(body.correlation_id) ?? null;
	if (response.ok && !body.error) {
		return { ok: true, data: body.data as T, freshness: readFreshness(body) };
	}
	return { ok: false, failure: readFailure(response.status, body, correlationId) };
}

function readFailure(
	status: number,
	body: Record<string, unknown>,
	correlationId: string | null
): Failure {
	const error = (body.error ?? {}) as Record<string, unknown>;
	const declared = asString(error.kind);
	return {
		kind: declared && isFailureKind(declared) ? declared : kindForStatus(status),
		identifier: asString(error.id) ?? INTERNAL_IDENTIFIER,
		message: asString(error.message) ?? `the surface answered ${status}`,
		subject: asString(error.subject) ?? null,
		correlationId
	};
}

function readFreshness(body: Record<string, unknown>): Freshness | null {
	const revision = asString(body.revision);
	const confirmedAt = asString(body.confirmed_at);
	if (!revision || !confirmedAt) return null;
	return { revision, confirmedAt, mayBeStale: body.may_be_stale === true };
}

function asString(value: unknown): string | null {
	return typeof value === 'string' && value ? value : null;
}
