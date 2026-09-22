/**
 * The Model half of the annotation surface: the cache, and what a write forgets.
 *
 * D9 puts server state in the query cache and client state in the ViewModel,
 * and this is the seam between them. The ViewModel is handed an
 * :type:`AnnotationModel` and never learns what an HTTP request is; everything
 * that knows — the typed client, the cache key, the invalidation map — is here.
 *
 * Every write goes through :meth:`CanonApi.write`, so *"invalidate on settle"*
 * is not a discipline anybody has to remember: there is no path from this module
 * to the client that does not drop what the write made untrue. Promotion is the
 * one that drops more, and it drops more for a reason rather than out of
 * caution — it writes a durable rule into the specification, so the compiled
 * briefing, the search and every validation outcome in the project are answers
 * about a file that just changed.
 */

import type { CanonApi } from './index';
import type { AnnotationListing, ApiResult, RecordedAnnotation } from './types';

export interface AnnotationQuery {
	readonly kinds?: readonly string[];
	readonly states?: readonly string[];
}

/** What the ViewModel is given: eleven calls, and no idea what is behind them. */
export interface AnnotationGateway {
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
	/**
	 * Rescue an orphan by naming the subject it belongs on now (`anchor-resolution`).
	 *
	 * Deliberately on the **gateway** and not on the `AnnotationModel` the
	 * ViewModel is handed. D2 keeps `AnnotationViewModel` anchor-agnostic and
	 * this change must not be the one that teaches it about parts: re-anchoring
	 * is an operation on an *anchor*, the anchor is the view's half of the
	 * boundary, and the viewer is handed this one function by its route.
	 */
	reanchor(
		project: string,
		asset: string,
		annotation: string,
		body: unknown
	): Promise<ApiResult<RecordedAnnotation>>;
}

/**
 * The gateway over one API instance.
 *
 * A function rather than a class because it holds nothing: every call is the
 * client's, wrapped in the cache read or the invalidating write, and a second
 * instance over the same `CanonApi` behaves identically — which is what lets the
 * sheet and the viewer be handed one each without becoming two copies of the
 * truth.
 */
export function annotationGateway(api: CanonApi): AnnotationGateway {
	const thread = (project: string, asset: string) => ({ project, asset });
	return {
		list: (project, asset, query = {}, revision = '') =>
			api.annotations(project, asset, query, revision),
		create: (project, asset, body) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.createAnnotation(project, asset, body)
				)
			),
		reply: (project, asset, annotation, body) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.replyToAnnotation(project, asset, annotation, body)
				)
			),
		edit: (project, asset, annotation, body) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.editAnnotation(project, asset, annotation, body)
				)
			),
		withdraw: (project, asset, annotation) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.withdrawAnnotation(project, asset, annotation)
				)
			),
		move: (project, asset, annotation, body) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.moveAnnotation(project, asset, annotation, body)
				)
			),
		resolve: (project, asset, annotation, body) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.resolveAnnotation(project, asset, annotation, body)
				)
			),
		reopen: (project, asset, annotation) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.reopenAnnotation(project, asset, annotation)
				)
			),
		promote: (project, asset, annotation, body) =>
			written(
				api.write('promote-annotation', thread(project, asset), (client) =>
					client.promoteAnnotation(project, asset, annotation, body)
				)
			),
		reanchor: (project, asset, annotation, body) =>
			written(
				api.write('annotate', thread(project, asset), (client) =>
					client.reanchorAnnotation(project, asset, annotation, body)
				)
			)
	};
}

/** The outcome of a write, once the cache has forgotten what it made untrue. */
async function written(
	pending: Promise<{ readonly result: ApiResult<RecordedAnnotation> }>
): Promise<ApiResult<RecordedAnnotation>> {
	return (await pending).result;
}
