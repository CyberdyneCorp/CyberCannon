import { switchedTo } from './switch';
import { triageLink } from '$lib/triage';

export type WorkArea = 'assets' | 'triage';

export interface WorkAreaLink {
	readonly area: WorkArea;
	readonly label: string;
	readonly address: string;
	readonly current: boolean;
}

export function workAreaLinks(project: string, pathname: string): readonly WorkAreaLink[] {
	const root = `/p/${encodeURIComponent(project)}`;
	const current: WorkArea = pathname === `${root}/triage` ? 'triage' : 'assets';
	return [
		{ area: 'assets', label: 'Assets', address: switchedTo(project), current: current === 'assets' },
		{
			area: 'triage',
			label: 'Triage',
			address: triageLink({ project, kind: '', asset: '', owner: '' }),
			current: current === 'triage'
		}
	];
}
