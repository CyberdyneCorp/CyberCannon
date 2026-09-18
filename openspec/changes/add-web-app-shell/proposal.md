# Proposal

## Why

`deployment-operations` requires us to host "the web application", but only two of
its screens are specified — the model sheet and the 3D viewer. There is no
specification for the application those screens live inside: no way to find an
asset, no way to move between projects, no sign-in experience, no behaviour when a
list is empty or a request fails.

Two of the original asks sit entirely outside the requirement layer as a result.
The Cyberdyne design system appears in **one task line** and zero requirements, and
the selective-MVVM structure appears only in design documents. Nothing today
prevents a forked design system or an application written with a ViewModel per
route — and both are far cheaper to prevent than to unwind.

This is **roadmap position 6**, immediately before the model sheet, because the
sheet and the viewer are screens that need somewhere to be reached from. Building
them first produces two pages with no application around them.

## What Changes

- **An application shell** — routing, the project and asset addresses, and the
  frame every screen renders inside.
- **An asset browser** — list, filter by status, owner and tag, and search using the
  ranking `asset-lookup` already specifies. This is the first place a human, rather
  than an agent, can answer *"where is the mech scout"*.
- **A sign-in experience** — entering, leaving, and the case that actually matters:
  a session expiring while someone is midway through writing an annotation.
- **Deep links that survive** — an asset's address is its spec-declared identifier,
  which `http-api` already makes permanent, so a link pasted into Discord still
  resolves months later.
- **Empty, error and degraded states as first-class screens**, not spinners: a
  project with no assets yet, a search with no results, an unreachable API, a
  rebuilding index, a stale working copy.
- **The design system becomes a requirement**, not a task note: the application
  consumes `@cyberdynecorp/svelte-ui-core` and does not reimplement its primitives.

## Capabilities

### New Capabilities

- `app-navigation`: the addresses and the frame — project selection and switching,
  the asset page as the place everything about an asset converges, deep links that
  remain valid, and where a person is told what they are looking at.
- `asset-browser`: finding an asset as a human — listing, filtering, searching with
  the specified ranking, disclosure of how a result matched, and what is shown when
  there is nothing to show.
- `web-session`: signing in and out, what happens to unsaved work when a session
  expires, and what an unauthenticated visitor sees.

### Modified Capabilities

None. No earlier change is archived, so a delta against an unarchived capability
cannot be written; constraints on `http-api` and `asset-lookup` are stated here as
constraints on this surface.

## Non-goals

- **No new backend behaviour.** Every read this surface performs is already
  specified by `asset-lookup`, `http-api` and `hosted-repository`. If a screen needs
  something the API does not expose, that is a gap in those capabilities, not work
  for this change.
- **No annotation, no sheet, no viewer.** Those are `add-model-sheet-2d` and
  `add-viewer-3d`. This change delivers the places they are reached from.
- **No admin or settings surface** — no project creation UI, no actor-mapping
  editor, no role administration. Those depend on decisions still open.
- **No realtime presence, no notifications beyond what `asset-requests` specifies.**
- **No offline mode and no installable app.**
- **No design system changes.** If a primitive is missing, it is raised against the
  component library, not forked here.

## Impact

- **New code** — `apps/cybercanon/web/`: routes, `lib/api/` typed clients,
  `lib/components/`, a thin server-state cache with invalidation.
- **New dependencies** — SvelteKit, the two `@cyberdynecorp` packages, a query cache.
- **Extends** — nothing in the backend. This change is the first that is purely a
  consumer of surfaces already specified, which makes it the real test of whether
  `http-api` exposes enough to build against.
