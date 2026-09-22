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
	type AnchorResolutions,
	type AnnotationListing,
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
	type PreviewContent,
	type PreviewDescriptor,
	type RecordedAnnotation,
	type RecordedRequest,
	type RequestListing,
	type SearchHit,
	type StatusReport,
	type TriageQueue,
	type UnreadItems,
	type ValidationOutcome,
	type WriteOutcome,
	type AssetRequest
} from './types';
import { INTERNAL_IDENTIFIER, isFailureKind, kindForStatus } from './outcomes';

export const AUTHORIZATION_HEADER = 'Authorization';
export const IDEMPOTENCY_HEADER = 'Idempotency-Key';
export const CORRELATION_HEADER = 'X-Correlation-Id';

/**
 * The deployment's own report. Unversioned on purpose — it describes the
 * deployment rather than the surface — which is why it is the one path this
 * client addresses outside the version segment.
 */
export const STATUS_PATH = '/status';

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

/** Whether a path sits under the version segment. Everything but `/status` does. */
interface Addressing {
	readonly versioned?: boolean;
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

	/**
	 * One asset's threads, filtered by the same vocabulary every surface uses.
	 *
	 * The filter is sent and never applied here: `model-sheet-2d` requires the
	 * sheet and any other surface to present *"the same set of annotations"* for
	 * one filter, and a client that narrowed a second time would be the place
	 * they stopped agreeing.
	 */
	listAnnotations(
		project: string,
		asset: string,
		options: AnnotationQuery = {}
	): Promise<ApiResult<AnnotationListing>> {
		return this.#get(`${annotations(project, asset)}`, annotationParameters(options));
	}

	/**
	 * What the 3D viewer loads, where it came from, and what its export measured.
	 *
	 * Three reads and no fourth: there is no method here that addresses a working
	 * export, and there is no address on the surface that would answer one (D7).
	 */
	readPreview(project: string, asset: string): Promise<ApiResult<PreviewDescriptor>> {
		return this.#get(preview(project, asset));
	}

	readPreviewContent(project: string, asset: string): Promise<ApiResult<PreviewContent>> {
		return this.#get(`${preview(project, asset)}/content`);
	}

	readAnchorResolutions(project: string, asset: string): Promise<ApiResult<AnchorResolutions>> {
		return this.#get(`${preview(project, asset)}/resolutions`);
	}

	readTriage(project: string, options: TriageQuery = {}): Promise<ApiResult<TriageQueue>> {
		return this.#get(`/projects/${enc(project)}/triage`, triageParameters(options));
	}

	/**
	 * The projects this credential may read, as the deployment reports them.
	 *
	 * It is authenticated and it applies the same read decision every other read
	 * applies, so it names the entitled projects and no others — which is what
	 * makes it safe to build a project switcher out of.
	 */
	readStatus(): Promise<ApiResult<StatusReport>> {
		return this.#get(STATUS_PATH, {}, { versioned: false });
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

	createAnnotation(
		project: string,
		asset: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('POST', annotations(project, asset), body, options);
	}

	replyToAnnotation(
		project: string,
		asset: string,
		annotation: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('POST', `${one(project, asset, annotation)}/replies`, body, options);
	}

	editAnnotation(
		project: string,
		asset: string,
		annotation: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('PATCH', one(project, asset, annotation), body, options);
	}

	withdrawAnnotation(
		project: string,
		asset: string,
		annotation: string,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('DELETE', one(project, asset, annotation), null, options);
	}

	moveAnnotation(
		project: string,
		asset: string,
		annotation: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('POST', `${one(project, asset, annotation)}/anchor`, body, options);
	}

	/**
	 * Rescue an orphan by naming the subject it belongs on now.
	 *
	 * Its own address rather than `\u007banchor\u007d`, because it is not the same
	 * operation: a move is *its author* putting their own pin somewhere else, and
	 * a re-anchor is anybody with write access rescuing a thread whose part is
	 * gone — attributed as a re-anchoring, and refused for an automated caller
	 * acting on its own.
	 */
	reanchorAnnotation(
		project: string,
		asset: string,
		annotation: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('POST', `${one(project, asset, annotation)}/reanchor`, body, options);
	}

	resolveAnnotation(
		project: string,
		asset: string,
		annotation: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('POST', `${one(project, asset, annotation)}/resolution`, body, options);
	}

	reopenAnnotation(
		project: string,
		asset: string,
		annotation: string,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('DELETE', `${one(project, asset, annotation)}/resolution`, null, options);
	}

	/**
	 * The one exit this client cannot make available to everybody.
	 *
	 * It is an ordinary call — the refusal is the system's, not the client's —
	 * and that is `model-sheet-2d`'s point in so many words: *"hiding an action
	 * SHALL NOT be the only enforcement"*. The panel offers it to a director;
	 * this method exists for anybody, and the server decides.
	 */
	promoteAnnotation(
		project: string,
		asset: string,
		annotation: string,
		body: unknown,
		options: WriteOptions = {}
	): Promise<ApiResult<RecordedAnnotation>> {
		return this.#send('POST', `${one(project, asset, annotation)}/promotion`, body, options);
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

	#get<T>(
		path: string,
		parameters: Record<string, string> = {},
		addressing: Addressing = {}
	): Promise<ApiResult<T>> {
		const search = new URLSearchParams(parameters).toString();
		return this.#request<T>(
			'GET',
			`${path}${search ? `?${search}` : ''}`,
			undefined,
			{},
			addressing
		);
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
		options: WriteOptions,
		addressing: Addressing = {}
	): Promise<ApiResult<T>> {
		const version = addressing.versioned === false ? '' : `/${SURFACE_VERSION}`;
		const url = `${this.#baseUrl}${version}${path}`;
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

function preview(project: string, asset: string): string {
	return `/projects/${enc(project)}/assets/${enc(asset)}/preview`;
}

function annotations(project: string, asset: string): string {
	return `/projects/${enc(project)}/assets/${enc(asset)}/annotations`;
}

function one(project: string, asset: string, annotation: string): string {
	return `${annotations(project, asset)}/${enc(annotation)}`;
}

/** What a thread listing may be narrowed by — the kinds, and the exit states. */
export interface AnnotationQuery {
	readonly kinds?: readonly string[];
	readonly states?: readonly string[];
}

/** What the art director's pass may be narrowed by. */
export interface TriageQuery {
	readonly kind?: string;
	readonly asset?: string;
	readonly owner?: string;
}

function annotationParameters(options: AnnotationQuery): Record<string, string> {
	const parameters: Record<string, string> = {};
	if (options.kinds?.length) parameters.kind = options.kinds.join(',');
	if (options.states?.length) parameters.state = options.states.join(',');
	return parameters;
}

function triageParameters(options: TriageQuery): Record<string, string> {
	const parameters: Record<string, string> = {};
	if (options.kind) parameters.kind = options.kind;
	if (options.asset) parameters.asset = options.asset;
	if (options.owner) parameters.owner = options.owner;
	return parameters;
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
