# Tasks

## 1. Application shell and routing

- [x] 1.1 Scaffold `apps/cybercanon/web/` as a SvelteKit + TypeScript application and verify `just web` serves it from a clean checkout after `just setup`
- [ ] 1.2 Add the two `@cyberdynecorp` packages against the GitHub registry and verify the foundation styles load and a library component renders
- [x] 1.3 Define the address scheme for project, asset and surface (D3) and verify each address resolves to its screen and reloads unchanged
- [x] 1.4 Implement the closed route-state set — content, empty, forbidden, not-found, degraded, failed (D6) — and verify a route cannot resolve outside it
- [x] 1.5 Implement route-level code splitting so the viewer scene module loads only on the viewer surface (D7) and verify the browser route's bundle excludes it
- [x] 1.6 Add the D1 structural test asserting no ViewModel exists outside the annotation module
- [x] 1.7 Add the D4 test failing the build when a local component reimplements a design-system primitive, with an explicit waiver mechanism requiring an upstream reference

## 2. Typed API client and server-state cache

- [x] 2.1 Generate or hand-write the typed client for the `http-api` surface under `lib/api/` and verify its types match the API's documented shapes
- [x] 2.2 Implement the single query cache keyed by resource (D2) and verify no component or ViewModel holds server state directly
- [x] 2.3 Implement the invalidation map and verify, per write path, that a test asserts exactly which cached resources it invalidates
- [x] 2.4 Implement uniform handling of the API's outcome vocabulary (not found, forbidden, unauthenticated, invalid, conflict, unavailable) mapping each to a route state, and verify each maps to its intended screen

## 3. Session experience

- [x] 3.1 Implement the unauthenticated landing offering sign-in with no project or asset content visible, and verify no content leaks before authentication
- [x] 3.2 Implement return-to-intended-address after sign-in and verify a deep link to an asset arrives there after authenticating
- [x] 3.3 Implement in-place re-authentication holding the in-flight request with its payload (D5) and verify an annotation typed before expiry is submitted intact afterwards
- [x] 3.4 Verify declining re-authentication leaves the input on screen and unsubmitted
- [x] 3.5 Implement sign-out clearing all cached project and asset content and verify nothing remains reachable without signing in again
- [x] 3.6 Display the acting identity on every authenticated screen and verify it matches the session's person
- [x] 3.7 Implement the early warning for a person with no mapped git identity, naming the unavailable actions, and verify it appears before any write is attempted
- [x] 3.8 Verify reads continue during an identity provider outage with the unavailability stated

## 4. Asset browser and search

- [x] 4.1 Implement the project-scoped listing showing name, identifier, status and owners, and verify against a project of mixed statuses
- [x] 4.2 Implement filtering by status, owner and tag using the specified filters, with each active filter visible and individually removable; verify removing one leaves the others applied
- [x] 4.3 Put filter and query state in the address (D3) and verify a filtered listing opened by another person shows the same filters
- [x] 4.4 Render search results in the order the specified ranking returns, with no client-side re-sorting; verify with a query matching by identifier and by description
- [x] 4.5 Disclose alias, tag and description matches, and mark results matching an unaccepted suggestion; verify each disclosure
- [x] 4.6 Implement the no-results screen stating the query and offering to clear filters, and the distinct filters-excluded-matches variant; verify both
- [x] 4.7 Implement the no-assets-yet screen naming how an asset comes to exist, and verify it on an empty project
- [x] 4.8 Implement degraded search disclosure for a rebuilding index and an unavailable delegated search, and verify partial results are never presented as complete

## 5. Project navigation

- [x] 5.1 Implement project selection and switching, and verify listing, filter and search state are discarded across a switch
- [x] 5.2 Verify switching project with an asset open lands on the new project's browser rather than a missing asset
- [x] 5.3 Display the owning project on every asset screen and verify it is present on each
- [x] 5.4 Implement distinct not-found and not-permitted screens and verify neither reveals the name or content of an asset the person may not read

## 6. The asset page

- [x] 6.1 Implement the asset page presenting identity, status, the three owners, effective constraints, open annotations, views, exports with validation outcome, and links; verify each section against a fully populated asset
- [x] 6.2 Verify absent content is stated rather than omitted, using an asset with no exports and no annotations
- [x] 6.3 Provide the entry points from which the model sheet and the 3D viewer are reached, and verify each address opens its surface
- [x] 6.4 Implement address-restores-the-view including surface selection, with degradation to the default view when the named surface no longer exists; verify both

## 7. Acceptance

- [x] 7.1 Verify the application at phone width and on a tablet: the browser, asset page and session flows remain usable, with no horizontal scrolling of the page body
- [x] 7.2 Verify every screen in the closed route-state set has been implemented, by enumerating states per route in a test rather than by inspection
- [ ] 7.3 Run the acceptance test: a developer who has never seen the tool finds a named asset, reads its constraints and opens its concept, without being told where to click
- [x] 7.4 Run `just check` and confirm `openspec validate --all --strict`, the test suite and the D1/D4 structural tests all pass
