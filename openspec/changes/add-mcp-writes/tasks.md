# Tasks

## 1. Domain — observations, attribution and write policy

- [ ] 1.1 Add `author_kind` (`human | agent`) to the annotation entry and a closed `ObservationKind` enumeration (`unattainable_constraint | ambiguity | defect`); verify a test asserts an unknown kind cannot be constructed and that `lint-imports` still reports zero third-party imports in the domain
- [ ] 1.2 Make the write attribution require both slots (D4) and verify a test asserts there is no constructor path producing a write attribution without a person or without an agent
- [ ] 1.3 Implement the policy that an automated caller may not create, modify or delete a constraint, rule, budget, status or owner, and may not resolve, promote, close or reopen any annotation including its own; verify it refuses for every role in turn
- [ ] 1.4 Implement the policy that an automated caller may only write against an existing asset; verify a test asserts no code path creates an asset or a specification file
- [ ] 1.5 Implement `WritePolicy` as a pure function over actor, asset, existing observations and a clock (D9), returning allowed or refused-with-reset-time; verify limits with a fake clock at the boundary, one over, and after reset
- [ ] 1.6 Implement near-duplicate suppression as a pure predicate over normalised text, asset, target, kind and agent, comparing only against **open** observations from the same agent (D10); verify an identical repeat suppresses, a repeat after resolution does not, and another agent's identical text does not suppress
- [ ] 1.7 Implement the unanchored-observation case: an unresolvable target is preserved as given and marked unanchored; verify no observation is ever attached to a different target

## 2. Application — credential, write ports and use cases

- [ ] 2.1 Define the `CredentialStore` port (get, set, clear) and the `DeviceAuthorizationFlow` port (D5) with in-memory fakes under `application/testing/`; verify both pass a port-conformance test
- [ ] 2.2 Define the `AnnotationWriter` port (append an annotation to an existing asset) and the `OutcomeReporter` port (deliver an outcome, list pending) with in-memory fakes (D1); verify the fakes pass the same conformance suite the real adapters will
- [ ] 2.3 Implement `record_observation`: resolve actor → require identity → authorize → check asset exists → apply `WritePolicy` → apply duplicate suppression → append with two-party attribution; verify each refusal path records nothing, and verify the ordering with a test asserting an unknown asset is refused before the rate limit is consumed
- [ ] 2.4 Verify identity gating: a test with no credential asserts every read use case succeeds and both write use cases are refused with a message naming the sign-in action
- [ ] 2.5 Verify an expired or unrefreshable credential refuses writes as unverifiable while reads continue, reusing the resolution chain from the read change
- [ ] 2.6 Verify that an actor, agent or author supplied as a parameter or embedded in the observation text has no effect on the recorded attribution
- [ ] 2.7 Implement `report_validation_outcome` taking an already-produced verdict; verify a test asserts no validation rule is evaluated during reporting and that the reported outcome equals the local verdict exactly
- [ ] 2.8 Implement outcome identity as (asset, export content hash, verdict hash) (D7); verify re-reporting an identical outcome yields exactly one record and a re-export yields a distinguishable second one
- [ ] 2.9 Implement `sign_in`, `sign_out` and `show_identity` use cases over the credential ports; verify sign-out clears the stored credential and that a subsequent write is refused while reads succeed

## 3. Adapters — credential, annotation write-back and outbox

- [ ] 3.1 Implement the operating-system credential store adapter; verify a round-trip test on the developer platform and a test asserting that an unavailable keychain reports writes unavailable with a reason rather than falling back to a file
- [ ] 3.2 Implement the device authorization flow adapter against CyberdyneAuth; verify with a stubbed authorization server that a code and URL are presented, polling honours the server's interval, and no secret is read from the terminal
- [ ] 3.3 Implement `GitAnnotationWriter` appending to the `annotations` block of the asset's specification file with comments and formatting preserved, without staging or committing (D2); verify a round-trip test asserts the rest of the file is byte-identical
- [ ] 3.4 Verify the writer refuses on a conflicted or unmergeable specification file, reports the condition, and leaves the file untouched
- [ ] 3.5 Implement the local report outbox as a git-ignored newline-delimited file under `.canon/` with an opportunistic flush (D6); verify a delivery failure retains the record, a later flush delivers it, and the file is absent from `git status`
- [ ] 3.6 Verify the outbox is bounded and self-healing: a test asserts a corrupt line is reported and skipped rather than blocking delivery of the rest

## 4. Adapters — MCP write tools

- [ ] 4.1 Implement `add_annotation(asset, target, text, kind)` as a thin call into `record_observation`, taking the agent identifier from launch configuration only (D4); verify a test asserts the adapter reads no agent identifier from tool arguments
- [ ] 4.2 Implement `report_export(asset, path, result)` calling the existing validation use case for the verdict and `report_validation_outcome` for delivery; verify the tool returns success when the destination is unreachable and states that the verdict stands and delivery is pending
- [ ] 4.3 Refuse writes when the server was launched without an agent identifier, naming the missing identifier, while reads continue; verify both halves in one test
- [ ] 4.4 Extend the exact-match tool-name test by exactly two entries and refine the clean-tree assertion so read tools leave the tree clean and a write tool's only permitted change is the annotations block of the named asset (D3); verify a test rejects any other changed path or block
- [ ] 4.5 Add the prohibition tests: no promotion tool exists, a caller acting as an art director is refused promotion, and an observation whose text asks for a constraint change alters no constraint
- [ ] 4.6 Verify legible refusals: unknown asset offers the closest identifiers, unknown kind lists the permitted kinds, a throttled write names the limit and its reset time, and no refusal ends the session
- [ ] 4.7 Verify the D1 structural test still holds with writes present — the MCP adapter contains no conditional on specification content and imports nothing from `adapters/outbound/`

## 5. Human surfaces — agent authorship is visible

- [ ] 5.1 Mark agent authorship in the open-annotations read and in the compiled briefing; verify a test with one human-authored and one agent-authored open annotation asserts exactly one is marked
- [ ] 5.2 Verify an agent-authored observation obeys the two-exit discipline: resolving it removes it from subsequent compilations, and promoting it attributes the resulting rule to the promoting person and not to the agent
- [ ] 5.3 Verify an unanchored observation is reported as unanchored wherever annotations are read, with the target as given preserved

## 6. CLI, wiring and acceptance

- [ ] 6.1 Add `canon login`, `canon logout` and `canon whoami`; verify via subprocess that login completes against a stubbed authorization server, whoami names the person and the pending report count, and logout leaves reads working
- [ ] 6.2 Add `canon report flush` and verify it delivers retained outcomes, reports the delivered and still-pending counts, and exits zero when the destination is unreachable
- [ ] 6.3 Extend the composition root to bind `AnnotationWriter` and `OutcomeReporter` per surface (D1); verify a test resolves both write use cases for the MCP server and asserts the local bindings are selected
- [ ] 6.4 Verify the offline guarantee end to end: a subprocess test with all network access denied completes every read tool and `canon validate`, and refuses only the two write tools
- [ ] 6.5 Document the agent client configuration gaining an agent identifier and add the `.gitignore` entry for the outbox; verify a clean clone plus the documented launch command completes a read and a refused write
- [ ] 6.6 Run the acceptance test: a Blender agent modelling an asset it cannot fit in budget records one observation naming the conflict, reports its export outcome, and a human sees the observation marked agent-authored in the compiled briefing and gives it one of the two exits; record the observation volume of the session as the input to the rate-limit configuration
- [ ] 6.7 Run `openspec validate --all --strict`, the full test suite, `lint-imports` and the cognitive complexity check, and confirm the backend target of 15 per function holds
