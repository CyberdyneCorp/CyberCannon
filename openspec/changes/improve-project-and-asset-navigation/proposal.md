# Proposal

## Why

The deployed asset browser, model sheet, viewer, and triage queue are individually reachable, but their navigation does not form a usable workflow. The links to an asset's surfaces appear only on Overview, and a project screen has no direct links to Assets or Triage. A person who opens the sheet or viewer must use browser history or the address bar to move on.

## What Changes

- Keep project navigation visible on every authenticated project screen, with direct links to Assets and Triage and the current destination identified.
- Keep the three asset surfaces visible on every asset screen, with the current surface identified.
- Preserve the existing project and asset address scheme, including deep links to selected annotations.

## Capabilities

### New Capabilities

- `app-navigation`: Add persistent workflow navigation to the application navigation capability currently specified in `add-web-app-shell` but not yet synced to main specs.

### Modified Capabilities

None.

## Impact

Frontend Svelte components and their navigation tests. No HTTP contract, domain object, database schema, or deployment setting changes.

## Non-goals

- Repair concept image mirroring or preview storage; those failures were diagnosed separately.
- Change asset data, annotation behavior, permissions, or the project's visual language.

## Roadmap position

This follows M3 and precedes broader project-registry work. The first hosted review exposed navigation dead ends in the existing artist workflow, so it is a focused usability follow-up to the deployed shell.
