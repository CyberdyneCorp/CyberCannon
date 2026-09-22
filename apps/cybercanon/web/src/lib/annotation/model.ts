/**
 * What the ViewModel is allowed to know about the network: eleven methods.
 *
 * D1 says the ViewModel may not touch a DOM type, a canvas context or a
 * `three.js` object. This is the other edge of the same rule: it may not touch a
 * `fetch` either. It is handed an :type:`AnnotationModel` — the Model half of
 * MVVM — and everything it does to the server goes through one of these, so the
 * whole ViewModel suite runs with a plain object and no network, no cache and
 * no browser.
 *
 * The implementation over the real client is `$lib/api/annotations`, which is
 * where the query cache and the invalidation map live (D2, D9). Keeping the
 * interface here rather than there is deliberate: the ViewModel declares what it
 * needs, and the API layer satisfies it, rather than the ViewModel being shaped
 * by whatever the client happens to expose.
 */

import type { AnnotationListing, ApiResult, RecordedAnnotation } from '$lib/api';

export interface AnnotationQuery {
	readonly kinds?: readonly string[];
	readonly states?: readonly string[];
}

export interface AnnotationModel {
	list(
		project: string,
		asset: string,
		query?: AnnotationQuery,
		revision?: string
	): Promise<ApiResult<AnnotationListing>>;

	create(project: string, asset: string, body: unknown): Promise<ApiResult<RecordedAnnotation>>;

	reply(
		project: string,
		asset: string,
		annotation: string,
		body: unknown
	): Promise<ApiResult<RecordedAnnotation>>;

	edit(
		project: string,
		asset: string,
		annotation: string,
		body: unknown
	): Promise<ApiResult<RecordedAnnotation>>;

	withdraw(
		project: string,
		asset: string,
		annotation: string
	): Promise<ApiResult<RecordedAnnotation>>;

	move(
		project: string,
		asset: string,
		annotation: string,
		body: unknown
	): Promise<ApiResult<RecordedAnnotation>>;

	resolve(
		project: string,
		asset: string,
		annotation: string,
		body: unknown
	): Promise<ApiResult<RecordedAnnotation>>;

	reopen(
		project: string,
		asset: string,
		annotation: string
	): Promise<ApiResult<RecordedAnnotation>>;

	promote(
		project: string,
		asset: string,
		annotation: string,
		body: unknown
	): Promise<ApiResult<RecordedAnnotation>>;
}
