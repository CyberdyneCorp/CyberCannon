# Design

## Context

The viewer is a single vertical flex column and caps its canvas frame at 40rem. The model sheet already uses a responsive main/side grid. The asset overview uses one column even when its short fact sections could sit side by side.

## Decisions

1. Use the existing spacing, color, border, and type tokens. Keep the same neo-brutal treatment and semantic controls.
2. On wide screens, give the viewer a fluid model column and a bounded tool rail. The inspection summary shares the top row with the source figures; the discussion list and selected thread share a lower row.
3. Keep the canvas at its current 16:9 ratio while sizing it to its container. The scene's existing resize observer updates renderer and camera aspect when the layout changes.
4. At the existing 60rem breakpoint, stack all viewer regions and retain their reading order. Long export paths and annotation text wrap within their columns.
5. Use balanced columns for overview sections so a long constraints block does not leave an empty grid row beside it. Keep DOM and reading order intact. Tighten the heading and tab spacing. No content is hidden or collapsed.
6. A degraded route still lists every unavailable reason, but if its summary repeats a listed reason, show that sentence only once. Keep the warning's yellow treatment and reduce its padding so it does not dominate the asset workspace.

## Risks

The resized canvas changes its pixel dimensions and camera aspect. A browser test will check the visible frame and controls at desktop and narrow widths.
