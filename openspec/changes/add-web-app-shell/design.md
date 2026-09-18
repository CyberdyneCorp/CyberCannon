# Design

## Context

First change that is purely a **consumer** of surfaces already specified. It adds no
backend behaviour, which makes it the real test of whether `http-api` exposes enough
to build an application against — see `proposal.md — Why`.

It also has to carry two conventions that currently live only in prose: the design
system and the selective-MVVM structure. Neither is observable product behaviour, so
neither earns a requirement; both are enforced here by structure and by tests.

## Goals / Non-Goals

**Goals:**

- Give the model sheet and the 3D viewer somewhere to be reached from.
- Make the selective-MVVM boundary structural rather than a note in a document.
- Make empty, error and degraded states cheap to get right, so they stop being the
  screens nobody builds.

**Non-Goals:**

- No design system extension. A missing primitive is raised upstream.
- No server-side rendering strategy beyond what routing requires.
- No animation or transition system.

## Decisions

### D1 — The shell is plain Svelte components; MVVM is reserved for annotation

Routes, the browser, the asset page and session handling are ordinary components
with runes. The only ViewModel in the application is the shared
`AnnotationViewModel` owned by `add-model-sheet-2d`.

*Why:* runes are already a binding layer, so a ViewModel per route is pure overhead.
MVVM earns its place in exactly one spot — one ViewModel serving both the 2D sheet
and the 3D viewer, which is what makes "support 2D and 3D" cost far less than twice.
Spreading it everywhere destroys that argument by making it unremarkable.
**Alternative rejected:** a ViewModel per route for consistency, which buys
uniformity and pays for it in indirection on screens that have no second view.

*Enforced by:* a structural test asserting no `*.svelte.ts` ViewModel exists outside
the annotation module.

### D2 — Server state lives in one query cache, never in a ViewModel or a component

A single cache keyed by resource, with explicit invalidation after any write. The
`AnnotationViewModel` holds interaction state — selection, draft, filter — and reads
server state from the cache.

*Why:* the alternative is the same asset's status cached in three components that
disagree after a promotion. Putting server state in the ViewModel is worse: it makes
the ViewModel untestable without a network, which was the whole reason for having
one. **Cost accepted:** a cache invalidation map that must be kept honest, and a
test per write path asserting what it invalidates.

### D3 — The address is the state

Project, asset, surface, filters and query all live in the URL. Component state holds
nothing a reload should preserve.

*Why:* `app-navigation` requires shareable filtered listings and links that reopen
what the sharer saw. Making the URL the single source of screen state means those
requirements are satisfied by construction rather than by a synchronisation routine
that drifts. **Alternative rejected:** local state with URL synchronisation, which is
the same thing with an extra copy and a bug for every screen that forgets to sync.

### D4 — Design system consumption is asserted, not requested

The application imports from `@cyberdynecorp/svelte-ui-core` and
`@cyberdynecorp/svelte-ui-foundation`. A test fails the build when a local component
reimplements a primitive the library already provides.

*Why:* "use the design system" in a document is advice; a failing build is a
constraint. The failure mode this prevents is the slow fork — a local Button
"just for this one case", then five more, then a design system nobody uses.
**Cost accepted:** when the library genuinely lacks something, the test has to be
explicitly waived with a reference to the upstream request, which is the friction
that keeps the waiver honest.

### D5 — Expiry mid-edit is handled by holding the request, not by redirecting

An unauthorised response to a write is caught, the in-flight request is held with
its payload, re-authentication is offered in place, and on success the original
request is replayed.

*Why:* `web-session` requires that unsaved work survives expiry. The conventional
redirect-to-login loses the annotation the person just spent two minutes writing —
and losing someone's writing once is enough for them to stop using the tool.
**Cost accepted:** every write path must be replayable, which means writes carry an
idempotency key — already required by `http-api`.

### D6 — Empty, error and degraded states are route-level states, not conditionals

Each data-bearing route resolves to one of: content, empty, forbidden, not-found,
degraded, or failed. A screen is written against that closed set.

*Why:* `asset-browser` and `app-navigation` between them require distinct screens for
nothing-matched, filters-excluded-everything, no-assets-yet, not-permitted,
not-found, index-rebuilding and delegated-search-unavailable. Scattered `{#if}`
branches guarantee some of those are never built. A closed set means a missing
state is a compile-level omission. **Cost accepted:** more ceremony on the routes
that genuinely only ever have content.

### D7 — Route-level code splitting keeps the 3D bundle off every other screen

The viewer's scene module loads only on the viewer surface.

*Why:* a person browsing an asset list should not download a 3D engine. This is a
decision now rather than an optimisation later because it constrains where the
viewer module may be imported from, and retrofitting that boundary after the fact
means untangling imports across the whole application.

## Risks / Trade-offs

- **The design system lacks a primitive a screen needs** → raise upstream and waive
  the D4 test with a reference; the waiver is visible in review, which is the point.
- **`http-api` turns out not to expose enough to build a screen** → that is a gap in
  `http-api`, and this change is where it surfaces. Treat it as a spec change there,
  not as a query invented in the frontend.
- **D3 puts filter state in the URL, so a long filter set makes an ugly address** →
  accepted; shareability is worth more than a tidy URL.
- **D5's replay depends on idempotency keys surviving an index rebuild**, which
  `http-api` bounds — so a replay after a rebuild may be refused as conflicting. The
  person keeps their text and retries; the work is not lost, which is the requirement.
- **Cost accepted overall:** this change writes no backend behaviour, so its value is
  invisible in the API and entirely visible to people. It will feel like the least
  technical change and is the one that decides whether anyone adopts the product.

## Migration Plan

Additive. Nothing depends on this change until the model sheet lands, so it can be
built and deployed behind the existing authentication with only the browser and asset
page reachable.

## Open Questions

- **Whether the asset page shows the compiled briefing inline** or links to it. A
  presentation choice that changes no requirement.
- **How many recent projects to offer in the switcher.** Configuration.
