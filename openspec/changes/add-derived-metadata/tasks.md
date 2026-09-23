# Tasks

## 1. Configuration and ports

- [x] 1.1 Define the model configuration read from `CANON_LLM_ENABLED`, `CANON_LLM_BASE_URL`, `CANON_LLM_API_KEY`, `CANON_LLM_MODEL`, `CANON_LLM_VISION_MODEL`, `CANON_LLM_TIMEOUT_S`, `CANON_LLM_MAX_RETRIES`, defaulting to disabled; verify an empty environment yields a disabled configuration
- [x] 1.2 Define `LLMPort` and `VisionPort` (D2) returning a result carrying content or `Unavailable(reason)` over {disabled, misconfigured, unreachable, rejected, timeout, malformed} (D3); verify no model failure can propagate as an exception
- [x] 1.3 Provide in-memory fakes for both ports under `application/testing/`, including one that returns each `Unavailable` reason, and verify port-conformance tests pass against them
- [x] 1.4 Add `.env.example` documenting all seven variables with the disabled default, and verify a test asserts the documented names match those the configuration reads

## 2. Adapter — OpenAI-compatible client

- [x] 2.1 Implement the Chat Completions adapter with a plain HTTP client and no provider SDK (D1); verify a test asserts no vendor SDK appears in the dependency manifest
- [x] 2.2 Pass the configured model identifier through verbatim with no validation or branching; verify two different identifiers produce requests differing only in that field
- [x] 2.3 Implement multimodal image requests for `VisionPort` sending only the image bytes and a fixed instruction; verify the constructed request contains no specification content
- [x] 2.4 Implement the timeout and retry budget, retrying transient failures only and never retrying authentication or invalid-request rejections; verify attempt counts for a transient failure, a rejection and a timeout
- [x] 2.5 Map every failure mode to its `Unavailable` reason and verify each of the six reasons is produced by its corresponding condition
- [x] 2.6 Verify provider isolation: `lint-imports` forbids the HTTP client and the adapter package from being imported by `application` or `domain`

## 3. Domain — derived records, normalisation, acceptance

- [x] 3.1 Model `DerivedRecord` keyed by source content hash with provenance (model identifier, generated at, source hash) (D5) and verify equality is by content hash
- [x] 3.2 Implement alias normalisation and exclusion as pure functions — trim, lowercase, deduplicate, drop terms matching the asset's id, name or existing aliases (D11) — and verify existing aliases are never suggested
- [x] 3.3 Implement defensive parsing of the model's alias response, reporting `malformed` rather than partially accepting (D10); verify well-formed, partially malformed and entirely unparseable responses
- [x] 3.4 Model acceptance and rejection records keyed by `(content_hash, value)` (D6) and verify a rejection persists across regeneration of the same unchanged image
- [x] 3.5 Implement the policy that an automated caller may not accept a suggestion, and verify refusal for every role

## 4. Application — use cases

- [x] 4.1 Implement `describe_view` producing a description, tags and suggested aliases for one concept view, reusing an existing record for an unchanged image with no model call (D5); verify reuse and verify a changed image creates a distinct record
- [x] 4.2 Verify generation targets images only: a test asserts an asset with a mesh and no concept view reports no describable source and performs no rendering
- [x] 4.3 Implement `accept_suggestion` writing the accepted value into `asset.yaml` and recording who accepted it and when (D8); verify attribution is recorded and acceptance is refused with no resolvable person
- [x] 4.4 Implement partial acceptance and edit-before-accept, and verify accepting two of four suggestions writes exactly those two and that an edited value is written and attributed
- [x] 4.5 Implement `reject_suggestion` and verify the rejected value is not presented again for the same unchanged source
- [x] 4.6 Verify accepted content survives regeneration, image replacement and deletion of all derived records
- [x] 4.7 Extend `SearchIndex` with derived rows and add the sixth, lowest-priority cascade pass over suggested aliases with results flagged (D9); verify an accepted alias outranks a suggestion and that a suggestion-only match is disclosed
- [x] 4.8 Verify generation is never implicit: a test exercises read, list, search, validate and compile against an asset with no derived record and asserts zero model calls

## 5. Boundary enforcement

- [x] 5.1 Verify the compiler cannot express derived content (D4): assert the parsed specification type has no field able to hold it and that `compile_spec` has no dependency on `SearchIndex`
- [x] 5.2 Verify byte-identical compiled output with derived records present and absent, for an asset carrying descriptions, tags and suggestions
- [x] 5.3 Verify no lens exposes generated content, for each of the four lenses
- [x] 5.4 Verify core paths are model-independent: validation reports and compiled specifications are identical with model access enabled and disabled
- [x] 5.5 Verify generation leaves the working tree clean across an entire project

## 6. The asset.yaml writer

- [x] 6.1 Implement the round-trip surgical writer mutating only the target sequence (D7) and verify a file with comments and a specific key order shows only the added alias in its difference
- [x] 6.2 Implement atomic write via temporary file in the same directory followed by rename, and verify an interrupted write leaves the original file byte-identical and the suggestion still pending
- [x] 6.3 Verify the written alias is indistinguishable from a hand-written one and that the file contains no marker of model origin

## 7. Command line and acceptance

- [x] 7.1 Add `canon describe <asset>` and `canon suggest-aliases <asset>`, reporting unavailability with its reason when model access is off; verify the disabled path exits successfully with an explanatory message
- [x] 7.2 Add the acceptance and rejection commands, and verify a full generate → accept → search cycle ranks the accepted alias as an alias
- [ ] 7.3 Add an opt-in integration suite runnable against any configured compatible endpoint, and verify it passes against the on-prem gateway
- [ ] 7.4 Run the acceptance test on a real batch of undescribed concept views: measure how many suggested aliases were accepted unedited, and record rejected suggestions as evidence about prompt quality
- [x] 7.5 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check

## Notes

**7.3 and 7.4 are unchecked, and both for the same reason: no model endpoint is
reachable from the machine this was implemented on.** The opt-in suite asked for
by 7.3 exists (`tests/integration/test_model_endpoint.py`) and skips cleanly
with `CANON_LLM_ENABLED` unset, which is the default everywhere; what could not
be done is the second half of the sentence — *"verify it passes against the
on-prem gateway"*. The AminiLLM gateway at `10.10.20.4:4000` is behind Twingate
and did not answer, and no credential for it exists outside the gateway owner's
hands. 7.4's acceptance measurement — how many suggested aliases a person
accepts unedited, on a real batch — needs a real model for the same reason, and
a number produced against a fake would be a number about the fake.

Everything else is implemented and verified against the fakes, against the real
adapter over a recorded HTTP client, and against real files and a real
repository where the requirement is about a file.

**Re-checked in M4 and still true.** The credentials made available for M4 are
CyberArche's, not the model gateway's (`CANON_ARCHE_*`, no `CANON_LLM_*`), so
`CANON_LLM_ENABLED` is still unset everywhere and
`tests/integration/test_model_endpoint.py` still skips — 6 skipped in the M4
run, which is the opt-in behaviour 7.3 asks for minus the one clause that needs
a gateway. The model-independence half of the milestone *was* measured rather
than assumed: the compiled briefing is byte-identical with derived records
present and absent (sha256 `cef95ae9…`, 704 bytes both times, with the
generated description and its tags absent from the output), which is task 5.2
and the invariant M4 is accountable for.
