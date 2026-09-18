# Proposal

## Why

Search in CyberCanon is deliberately deterministic: human-written `aliases` plus
full text, chosen over embeddings because aliases are *correct* rather than
probabilistic. The cost of that choice is that **somebody has to write the
aliases**, and nobody will, for the two hundredth variation dropped into a folder
on a Friday. Unwritten aliases are how a deterministic search quietly becomes a
search that finds nothing.

A vision model looking at a concept view and proposing
`[mech, walker, quadruped, recon]` for one click of acceptance removes that cost
while keeping the search exact. That is the feature. Generated prose is a
by-product, useful for recall on assets nobody has described yet.

This change also settles **how CyberCanon talks to models at all** — one wire
format, configured by environment — before three features each pick their own
client. It sits outside the roadmap's numbered sequence because it is optional by
construction: every capability here degrades to absent, and nothing in validation,
compilation or lookup may depend on it.

## What Changes

- **One model interface: the OpenAI-compatible Chat Completions API**, behind
  `LLMPort` and `VisionPort`. The same build points at OpenAI, at the on-prem
  AminiLLM gateway, or at any compatible proxy.
- **Environment-driven configuration** — `CANON_LLM_ENABLED` (default **false**),
  `CANON_LLM_BASE_URL`, `CANON_LLM_API_KEY`, `CANON_LLM_MODEL`,
  `CANON_LLM_VISION_MODEL`, `CANON_LLM_TIMEOUT_S`, `CANON_LLM_MAX_RETRIES`.
- **Model identifiers are opaque strings** — passed through verbatim, never
  allow-listed, never branched on. A new model is a configuration change.
- **Derived metadata for a concept view** — a description, tags and **suggested
  aliases**, stored in the rebuildable index keyed by the blob's content hash.
- **Never in `asset.yaml`, never in `art-spec.md`.** Generated content is a
  proposal; the compiled briefing stays human-authored.
- **Acceptance is the bridge** — a person accepts a suggested alias and it is
  written into `asset.yaml` as ordinary authored content, attributed to them. Same
  two-exit discipline as annotations: promoted by a human, or it stays out.
- **Meshes use facts, not guesses** — `MeshFacts` already yields triangle counts,
  part names, materials and sockets deterministically. No turntable rendering, no
  mesh description.
- **Total degradation** — disabled, misconfigured, unreachable, timing out and
  rate-limited all behave identically: the feature is unavailable and everything
  else works.

## Capabilities

### New Capabilities

- `llm-integration`: how CyberCanon reaches a language or vision model — the
  OpenAI-compatible contract, environment configuration, opaque model identifiers,
  failure and degradation behaviour, and the rule that no provider detail escapes
  the adapter.
- `derived-metadata`: generating and storing descriptions, tags and suggested
  aliases — content-hash keying, provenance, regeneration, and the hard boundary
  keeping generated content out of authored specifications and compiled briefings.
- `metadata-acceptance`: how a person turns a suggestion into authored content —
  accept, reject, partial acceptance, attribution, and what happens when the
  underlying image changes afterwards.

### Modified Capabilities

None. Requirements touching the index and the command line are specified inside
the capabilities above, because `asset-lookup` and `canon-cli` belong to changes
that are not yet archived.

## Non-goals

Explicitly **not** in this change:

- **No automatic writing to `asset.yaml`.** Nothing generated reaches a
  specification file without a person accepting it.
- **No generated content in `art-spec.md`**, in any form, including as a labelled
  section. The briefing agents read stays human-authored.
- **No embeddings, no vector store, no semantic search.** This change feeds the
  existing exact search; it does not replace it.
- **No mesh description and no turntable rendering.** `MeshFacts` covers meshes.
- **No provider-specific features** — no function calling, no structured-output
  modes, no vendor extensions that a compatible proxy might not implement.
- **No agent-triggered generation.** Generation is a human or a pipeline action;
  an agent asking a model to describe an asset and having that become canon is the
  loop this project exists to prevent.
- **No prompt management UI, no per-project prompt tuning.** One prompt per task,
  in code, versioned with it.
- **No cost accounting or quota management.** A timeout and a retry budget are the
  whole failure policy.

## Impact

- **New code** — `libs/cybercanon/application/ports/{llm,vision}.py`; use cases
  `describe_view`, `suggest_aliases`, `accept_suggestion`, `reject_suggestion`;
  `libs/cybercanon/adapters/outbound/openai_compatible/`; extensions to the
  `SearchIndex` port for derived rows and their provenance.
- **New dependency** — an HTTP client only. **No provider SDK**: the
  OpenAI-compatible Chat Completions request is a documented JSON shape, and
  depending on a vendor SDK to send it would reintroduce the coupling this change
  exists to avoid.
- **Configuration** — seven environment variables, all optional, all defaulting to
  the feature being off. `.env.example` documents them.
- **Consumer-side impact** — none unless enabled. With it enabled, an asset gains
  suggestions visible where its metadata is shown, and an accepted alias produces a
  normal, reviewable `asset.yaml` diff authored by the person who accepted it.
