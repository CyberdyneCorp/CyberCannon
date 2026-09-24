# Design

## Decisions

1. Keep placement context in the shared thread panel as presentation derived from the draft anchor. The view model continues to carry anchors without inspecting their shape.
2. Focus the draft text field when a composer opens. Disable Save until text exists and while its write is pending; announce pending state in the composer.
3. Show 2D placement guidance under each image and name each pin by its kind, state, and text. Preserve the pin's placement and pointer isolation.
4. List 3D annotations by anchored part in the tool rail. Clicking an entry uses the existing `open` flow to restore camera and animation and select the discussion. Orphaned anchors remain labeled and available for rescue.
5. Use existing spacing and color tokens. Keep the rail compact and the narrow layout in document order.

## Risks

The rail may grow with many annotations. It remains a simple list so all entries are reachable and browser tests cover narrow layouts and save/reopen behavior.
