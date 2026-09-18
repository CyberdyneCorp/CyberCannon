# Tasks

## 1. Configuration and ports

- [ ] 1.1 Define the model configuration read from `CANON_LLM_ENABLED`, `CANON_LLM_BASE_URL`, `CANON_LLM_API_KEY`, `CANON_LLM_MODEL`, `CANON_LLM_VISION_MODEL`, `CANON_LLM_TIMEOUT_S`, `CANON_LLM_MAX_RETRIES`, defaulting to disabled; verify an empty environment yields a disabled configuration
- [ ] 1.2 Define `LLMPort` and `VisionPort` (D2) returning a result carrying content or `Unavailable(reason)` over {disabled, misconfigured, unreachable, rejected, timeout, malformed} (D3); verify no model failure can propagate as an exception
- [ ] 1.3 Provide in-memory fakes for both ports under `application/testing/`, including one that returns each `Unavailable` reason, and verify port-conformance tests pass against them
- [ ] 1.4 Add `.env.example` documenting all seven variables with the disabled default, and verify a test asserts the documented names match those the configuration reads

## 2. Adapter — OpenAI-compatible client

- [ ] 2.1 Implement the Chat Completions adapter with a plain HTTP client and no provider SDK (D1); verify a test asserts no vendor SDK appears in the dependency manifest
- [ ] 2.2 Pass the configured model identifier through verbatim with no validation or branching; verify two different identifiers produce requests differing only in that field
- [ ] 2.3 Implement multimodal image requests for `VisionPort` sending only the image bytes and a fixed instruction; verify the constructed request contains no specification content
- [ ] 2.4 Implement the timeout and retry budget, retrying transient failures only and never retrying authentication or invalid-request rejections; verify attempt counts for a transient failure, a rejection and a timeout
- [ ] 2.5 Map every failure mode to its `Unavailable` reason and verify each of the six reasons is produced by its corresponding condition
- [ ] 2.6 Verify provider isolation: `lint-imports` forbids the HTTP client and the adapter package from being imported by `application` or `domain`

## 3. Domain — derived records, normalisation, acceptance

- [ ] 3.1 Model `DerivedRecord` keyed by source content hash with provenance (model identifier, generated at, source hash) (D5) and verify equality is by content hash
- [ ] 3.2 Implement alias normalisation and exclusion as pure functions — trim, lowercase, deduplicate, drop terms matching the asset's id, name or existing aliases (D11) — and verify existing aliases are never suggested
- [ ] 3.3 Implement defensive parsing of the model's alias response, reporting `malformed` rather than partially accepting (D10); verify well-formed, partially malformed and entirely unparseable responses
- [ ] 3.4 Model acceptance and rejection records keyed by `(content_hash, value)` (D6) and verify a rejection persists across regeneration of the same unchanged image
- [ ] 3.5 Implement the policy that an automated caller may not accept a suggestion, and verify refusal for every role

## 4. Application — use cases

- [ ] 4.1 Implement `describe_view` producing a description, tags and suggested aliases for one concept view, reusing an existing record for an unchanged image with no model call (D5); verify reuse and verify a changed image creates a distinct record
- [ ] 4.2 Verify generation targets images only: a test asserts an asset with a mesh and no concept view reports no describable source and performs no rendering
- [ ] 4.3 Implement `accept_suggestion` writing the accepted value into `asset.yaml` and recording who accepted it and when (D8); verify attribution is recorded and acceptance is refused with no resolvable person
- [ ] 4.4 Implement partial acceptance and edit-before-accept, and verify accepting two of four suggestions writes exactly those two and that an edited value is written and attributed
- [ ] 4.5 Implement `reject_suggestion` and verify the rejected value is not presented again for the same unchanged source
- [ ] 4.6 Verify accepted content survives regeneration, image replacement and deletion of all derived records
- [ ] 4.7 Extend `SearchIndex` with derived rows and add the sixth, lowest-priority cascade pass over suggested aliases with results flagged (D9); verify an accepted alias outranks a suggestion and that a suggestion-only match is disclosed
- [ ] 4.8 Verify generation is never implicit: a test exercises read, list, search, validate and compile against an asset with no derived record and asserts zero model calls

## 5. Boundary enforcement

- [ ] 5.1 Verify the compiler cannot express derived content (D4): assert the parsed specification type has no field able to hold it and that `compile_spec` has no dependency on `SearchIndex`
- [ ] 5.2 Verify byte-identical compiled output with derived records present and absent, for an asset carrying descriptions, tags and suggestions
- [ ] 5.3 Verify no lens exposes generated content, for each of the four lenses
- [ ] 5.4 Verify core paths are model-independent: validation reports and compiled specifications are identical with model access enabled and disabled
- [ ] 5.5 Verify generation leaves the working tree clean across an entire project

## 6. The asset.yaml writer

- [ ] 6.1 Implement the round-trip surgical writer mutating only the target sequence (D7) and verify a file with comments and a specific key order shows only the added alias in its difference
- [ ] 6.2 Implement atomic write via temporary file in the same directory followed by rename, and verify an interrupted write leaves the original file byte-identical and the suggestion still pending
- [ ] 6.3 Verify the written alias is indistinguishable from a hand-written one and that the file contains no marker of model origin

## 7. Command line and acceptance

- [ ] 7.1 Add `canon describe <asset>` and `canon suggest-aliases <asset>`, reporting unavailability with its reason when model access is off; verify the disabled path exits successfully with an explanatory message
- [ ] 7.2 Add the acceptance and rejection commands, and verify a full generate → accept → search cycle ranks the accepted alias as an alias
- [ ] 7.3 Add an opt-in integration suite runnable against any configured compatible endpoint, and verify it passes against the on-prem gateway
- [ ] 7.4 Run the acceptance test on a real batch of undescribed concept views: measure how many suggested aliases were accepted unedited, and record rejected suggestions as evidence about prompt quality
- [ ] 7.5 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check
