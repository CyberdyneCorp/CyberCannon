# Design

## Context

The root SvelteKit layout already owns the project indicator and project switcher. `AssetOverview` owns the surface links, so they disappear when `AssetSurface` renders the sheet or viewer. Existing address helpers create project, asset, and triage URLs; the navigation can reuse them.

## Goals / Non-Goals

**Goals:** Put project work-area links in the shared frame and asset surface links around every asset surface. Show the active destination with a visible treatment and `aria-current="page"`.

**Non-Goals:** Change route loading, authorization, server data, or media retrieval.

## Decisions

- The project links live in `ProjectBar`, which already knows the current project. A small pure route helper derives whether the URL is in Assets or Triage. Links retain only the project identifier, so switching work areas clears route-specific filters.
- The asset links move from `AssetOverview` to a shared `AssetNavigation` rendered by `AssetSurface`. They use `AssetPage.surfaces` and the resolved surface already returned by the route. This keeps their availability and address policy in one place.
- Use ordinary anchors and `aria-current="page"`. They preserve deep-link behavior and browser history without local navigation state.

No domain value object or port is introduced or touched. The domain continues to decide asset content, authorization, and validation. These Svelte components are presentation adapters over existing route data.

## Risks / Trade-offs

- Extra header links can wrap at phone width → keep the project navigation in its own flexible row and check narrow rendering.
- Moving surface links could duplicate them on Overview → remove the old rendering from `AssetOverview` and verify each link occurs once.

## Migration Plan

The change is frontend-only and deploys with the web image. Rollback uses the previous web image; no data migration is needed.
