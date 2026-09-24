# Tasks

## 1. Asset layout

- [x] 1.1 Tighten the asset heading and surface navigation spacing; arrange overview sections in responsive balanced columns.
- [x] 1.2 Make the viewer canvas fluid, put tools beside it on wide screens, and preserve single-column order on narrow screens.
- [x] 1.3 Arrange annotation list and selected thread side by side on wide screens without losing accessible headings or controls.
- [x] 1.4 Remove duplicate degraded-route text and tighten its warning panel, with a regression test.
- [x] 1.5 Cap the wide 3D canvas height and redraw when its displayed size changes.
- [x] 1.6 Attach the annotation gateway on the asset route so Save sends 2D and 3D writes.
- [x] 1.7 Save 2D anchors with declared view names while keeping short slot labels in the sheet.
- [x] 1.8 Keep clicks on existing 2D pins from creating a new draft.

## 2. Verification

- [x] 2.1 Add layout regression coverage for desktop and narrow widths; run web checks and targeted browser tests.
- [x] 2.2 Update roadmap/spec counts and verify the deployed asset viewer after pushing and redeploying web.
- [x] 2.3 Exercise 2D strokes and 3D anchor creation through a real browser, including save and reload; verify the shorter viewport at all supported widths.
