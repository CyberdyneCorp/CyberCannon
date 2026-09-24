# Tasks

## 1. Camera navigation

- [x] 1.1 Redraw on orbit/pan/zoom control changes and expose zoom methods; add a browser regression test that verifies camera gestures visibly change the rendered frame.
- [x] 1.2 Add zoom buttons and concise mouse/touch instructions beside the canvas; verify drag navigation does not compose an annotation.

## 2. Inspection facts

- [x] 2.1 Inspect source glTF material texture channels and embedded image dimensions through the mesh-inspector port, preserving unknown dimensions and unsupported-format state; add adapter tests.
- [x] 2.2 Carry source texture summaries through the preview descriptor and typed web API without exposing image bytes; add use-case and HTTP tests.
- [x] 2.3 Count preview normal attributes and present source/preview triangles, texture dimensions, normal-map channels, and preview vertex normals with honest unavailable states; add component and browser tests.

## 3. Verification

- [x] 3.1 Generate features, update roadmap/spec counts, run focused web and Python tests, E2E browser cases, complexity checks, and strict OpenSpec validation.
- [ ] 3.2 Check the production `mech_scout` viewer after a validated release, if deployment is authorized.
