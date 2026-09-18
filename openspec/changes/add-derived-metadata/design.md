# Design

## Context

See `proposal.md — Why`. The standing rules this change implements are already in
`openspec/project.md`: derived metadata is a proposal, acceptance by a human is
the bridge, and LLM access is OpenAI-compatible and environment-driven.

One fact shapes the whole design: **this change touches `asset.yaml` with a
writer for the first time.** Every earlier change reads. A writer that reorders
keys or eats an artist's comments produces an unreviewable diff, and the tool
loses credibility on the first pull request it opens.

The deployment target is Coolify, which reinforces rather than complicates the
configuration decision: environment variables are how Coolify supplies
configuration, so the twelve-factor shape specified here is the native one.

## Goals / Non-Goals

**Goals:**

- Make "no model configured" the ordinary, fully-supported state.
- Make it structurally impossible for generated content to reach `art-spec.md`.
- Write to `asset.yaml` in a way that survives code review.
- Keep the vendor surface to one HTTP call shape.

**Non-Goals (design level):**

- No batching, no queue, no background worker. Generation is per-image and
  synchronous behind a timeout; a bulk operation is a loop with a progress line.
- No prompt experimentation framework. One prompt per task, in code.
- No caching layer beyond the content-hash keyed rows, which already are the cache.

## Decisions

### D1 — No provider SDK; a plain HTTP client against Chat Completions

The adapter constructs the documented JSON request itself and sends it with a
generic HTTP client.

*Why:* `llm-integration` requires that any compatible endpoint works. A vendor SDK
reintroduces exactly the coupling the requirement removes — SDKs add base-URL
quirks, auth assumptions, retry behaviour and version churn, in exchange for
convenience over a request body that is a dozen lines of JSON. **Alternative
rejected:** the official OpenAI SDK, which is pleasant and would quietly make the
on-prem gateway a second-class target.

### D2 — Two ports, not one

`LLMPort.complete(prompt) -> str` and `VisionPort.describe(image_bytes, prompt) -> str`.
Same adapter implements both.

*Why:* the vision model identifier is separately configured, and a deployment may
have text without vision. Two ports make "vision unavailable, text available" a
representable state rather than a special case inside one method.

### D3 — Availability is a value the caller receives, not an exception it catches

Ports return a result type carrying either content or an `Unavailable(reason)`
where reason ∈ {disabled, misconfigured, unreachable, rejected, timeout,
malformed}. No model failure raises past the adapter.

*Why:* `llm-integration` requires that every failure degrade identically and that
a larger operation completes regardless. A result type makes forgetting to handle
it a visible omission; an exception makes forgetting it the default. It also gives
the "state the reason" requirement somewhere to live.

### D4 — Generated content is physically unable to reach the compiler

`compile_spec` takes the parsed specification, and the parsed specification type
has no field that can hold derived content — derived rows live in the index,
reachable only through `SearchIndex`, which the compiler does not depend on.

*Why:* `derived-metadata` requires byte-identical compiled output with and without
generated metadata present. A filter in the compiler could be bypassed by a later
change; a type that cannot express the content cannot be. The test asserting
byte-identical output is the belt; this is the braces.

### D5 — Derived rows are keyed by `sha256(image bytes)`, not by asset or path

Row key is the content hash. Renaming a view file, moving an asset or duplicating
the same image across assets all resolve to the same derived content.

*Why:* it makes "unchanged image is not regenerated" exact and free, gives
regeneration idempotence, and means a replaced image cannot silently inherit the
previous image's description — a real risk when the whole point is that a
description must correspond to what was actually seen.

### D6 — Acceptance and rejection are recorded against `(content_hash, value)`

Not against the asset. A rejected term stays rejected for that image;
regenerating produces the same rows and the rejection still applies.

*Why:* the spec requires rejected suggestions not to return for the same unchanged
source. Keying on the asset would resurrect rejections whenever a row was rebuilt.

### D7 — The `asset.yaml` writer is round-trip, surgical, and atomic

`ruamel.yaml` round-trip mode (chosen in change 1 precisely for this moment),
mutating only the target sequence, written to a temporary file in the same
directory and atomically renamed over the original.

*Why:* the spec requires that only the intended change appears in the diff and that
a failed write leaves the file untouched. Round-trip mode gives the first;
write-temp-then-rename gives the second, including against a crash. **Alternative
rejected:** load-and-dump with a standard YAML library, which is three lines
shorter and rewrites every file it touches.

### D8 — Acceptance provenance lives in the index, and the file carries no marker

The specification records the alias; the index records who accepted what, when,
and from which derived row.

*Why:* `metadata-acceptance` requires the accepted value to be indistinguishable
from a hand-typed one — because it *is* the person's value now; they took
responsibility for it. A marker in the file would re-open the question every time
someone read it, and would leak a derived concern into the source of truth. Git
already records who committed the change; the index adds who clicked accept, which
may be a different action at a different time.

### D9 — Suggested aliases search as a disclosed last resort

The ranked cascade gains a sixth and final pass over suggested aliases, and results
from it are flagged.

*Why:* an unaccepted suggestion is the system guessing. It should be able to rescue
a search that would otherwise return nothing — that is the entire point of the
feature — but it must never quietly outrank something a person wrote, and the
person searching should know why a result appeared. It also feeds the
zero-result log honestly: a query rescued only by a suggestion is evidence that an
alias is missing.

### D10 — One prompt per task, in code, with the output shape validated

Prompts are constants beside the adapter. The alias prompt asks for a short list;
the response is parsed defensively and normalised, and anything unparseable is
reported as `malformed` rather than partially accepted.

*Why:* provider-agnostic means no structured-output mode and no function calling
(`llm-integration` forbids depending on them), so the response is text and must be
parsed. Failing closed on a malformed response is the conservative choice: a
half-parsed alias list is worse than none.

### D11 — Normalisation and exclusion happen in the domain, not the prompt

Lowercasing, trimming, deduplication, and removing terms already present as the
asset's id, name or aliases are pure functions applied after the model answers.

*Why:* the spec requires suggestions to be in specification form and to exclude
existing aliases. Asking a model politely not to repeat existing aliases is a
suggestion; filtering afterwards is a guarantee — and it is testable with no model.

## Risks / Trade-offs

- **Suggestions are plausible but wrong, and someone accepts them in bulk** →
  Acceptance is per value, never defaulted, never bulk-by-default, and the diff it
  produces goes through normal review. The accepting person's name is on it.
- **The feature becomes load-bearing and the "optional" claim rots** → The
  byte-identical compiled-output test and the "reads never generate" test both fail
  the moment something in a core path starts depending on a model.
- **A compatible endpoint is compatible only in name** (subtle differences in
  multimodal message formatting are the usual offender) → Keep the request to the
  documented minimum, and add an integration test suite that can be pointed at any
  endpoint to confirm it serves this system.
- **Image bytes sent to a third-party endpoint** → Scope is specified and tested
  (image plus fixed instruction, nothing else), the master switch defaults to off,
  and pointing the base URL at the on-prem gateway makes this a deployment
  decision rather than a product one.
- **Cost accepted:** two storage locations for things a user thinks of as one —
  the suggestion in the index, the accepted value in the file. That split *is* the
  feature, and the acceptance record in D8 is what keeps the two joinable.

## Migration Plan

Additive and inert by default: with `CANON_LLM_ENABLED` unset, nothing in this
change executes. Enabling it creates derived rows in the existing index, which is
already specified as disposable. Rollback is unsetting the switch; accepted aliases
remain because they are authored content, which is the intended outcome.

## Open Questions

- **How many aliases to suggest per image.** A prompt and normalisation constant;
  answerable from the first real batch, and it changes no specification.
- **Whether the description text is worth keeping at all** once alias suggestion
  proves itself. If the zero-result log shows descriptions never rescue a search,
  the description can be dropped without touching `metadata-acceptance`.
