# Design

## Context

The viewer is a single vertical flex column and caps its canvas frame at 40rem. The model sheet already uses a responsive main/side grid. The asset overview uses one column even when its short fact sections could sit side by side.

## Decisions

1. Use the existing spacing, color, border, and type tokens. Keep the same neo-brutal treatment and semantic controls.
2. On wide screens, give the viewer a fluid model column and a bounded tool rail. The inspection summary shares the top row with the source figures; the discussion list and selected thread share a lower row.
3. Keep the canvas at 16:9 on narrow screens. On wide screens, cap its height at the lesser of 46vh and 32rem, with a 20rem floor, so annotation controls enter the first screen. The scene observes canvas size changes and updates renderer and camera aspect.
4. At the existing 60rem breakpoint, stack all viewer regions and retain their reading order. Long export paths and annotation text wrap within their columns.
5. Use balanced columns for overview sections so a long constraints block does not leave an empty grid row beside it. Keep DOM and reading order intact. Tighten the heading and tab spacing. No content is hidden or collapsed.
6. A degraded route still lists every unavailable reason, but if its summary repeats a listed reason, show that sentence only once. Keep the warning's yellow treatment and reduce its padding so it does not dominate the asset workspace.
7. Connect the route's annotation gateway to the shared view model once per asset. Surface changes retain an in-progress draft; navigating to another asset resets it. The same gateway serves 2D and 3D writes.
8. The sheet may display a short image slot, but its 2D anchor uses the exact declared view name from the asset. The server validates that identity; image slot names only address rendered media.
9. The isolated end-to-end Git daemon has a mapped fixture actor and accepts pushes to its checked-out test branch, allowing browser saves to exercise the actual repository write path.
10. An existing 2D pin consumes pointer presses before they reach the image placement handler, so opening a thread cannot start a second draft.

## Risks

The resized canvas changes its pixel dimensions and camera aspect. Browser tests check frame height, controls, resizing, and 2D and 3D annotation saves across the viewport matrix.
