# Tasks

## 1. Concept references

- [x] 1.1 Add typed, cached reads for current view history and image bytes; verify authenticated URL and failure tests in the web client suite.
- [x] 1.2 Resolve sheet images only in the browser, without making one image failure fatal; verify route load tests for sheet, overview, viewer, and partial failure.
- [x] 1.3 Group path and slot aliases into one image card while preserving old pins and canonical new anchors; verify sheet rendering and mapping tests.

## 2. 3D previews

- [x] 2.1 Ship the pinned Draco decoder with the web build and configure both preview parse paths; verify a real compressed GLB parses in a browser test.
- [x] 2.2 Explain preview decode failures beside Retry without hiding annotations; verify a regression test for the error state.

## 3. Release checks

- [x] 3.1 Regenerate OpenSpec features, update roadmap counts, and verify OpenSpec and repository gates.
- [x] 3.2 Check responsive sheet and viewer presentation, then verify the deployed asset's image and 3D preview if the release is authorized.
