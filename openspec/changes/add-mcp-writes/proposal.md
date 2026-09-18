# Proposal

## Why

The read surface gave agents the constraints. It left them with no way to say the
one thing an agent is uniquely placed to notice: **"I cannot satisfy this."** A
modelling agent that cannot reach 12k triangles without destroying the head
silhouette currently has exactly two options — silently miss the budget, or
silently wreck the silhouette. Both discoveries land days later, on a human, which
is the original cost this project exists to delete.

The second gap is quieter. `canon validate` produces a verdict on a developer's
machine and that verdict dies there. Nobody can answer *which assets are currently
failing* without walking the repository, because no run is ever reported.

This is **roadmap position 6, and it is last on purpose.** The dangerous version of
this change is the one written in week one, when "let the agent fix the spec so the
export passes" still sounds like helpfulness. Positions 1–5 establish that the
specification is the authority and that agents read it; only after that is a write
surface safe to open, and only in the shape that does not undo it. Every tool here
is **proposal-shaped**: an agent may record an observation and report an outcome,
and a human remains the only path from either one into the canon.

A third reason to do it now rather than later: writes are the first thing in the
product that requires an identity, and the credential flow they need — device code
once, refresh token in the operating system's credential store — is the same one
the artist-facing surfaces will use. Settling it against two narrow tools is
cheaper than settling it against a web application.

## What Changes

- **Exactly two write tools, and the number is a specified maximum, not a
  starting point** — `add_annotation(asset, target, text, kind)` and
  `report_export(asset, path, result)`. Nothing else, in this or any later version.
- **`add_annotation` records an observation** — typically that a declared
  constraint is unattainable, with the reason. It anchors to a target the way any
  annotation does, and it enters the same two-exit triage: a human promotes it to a
  rule or resolves it as an issue. The agent gets neither exit.
- **`report_export` reports a verdict that was already produced locally.** The
  validation decision remains offline, identity-free and authoritative; reporting
  is an after-the-fact delivery that may fail, retry, or never arrive without
  changing anything a person sees on their own machine.
- **Writes require an identity; reads still do not.** An unauthenticated agent
  keeps the entire read surface and loses exactly these two tools, with a message
  saying how to sign in.
- **One credential for the machine** — obtained once through a device
  authorization flow, with the refresh token held in the operating system's
  credential store and shared by the `canon` command line and the MCP server, so
  an agent configuration never contains a secret.
- **Two-party attribution is enforced at the write, not at the render** — every
  record names the person and the agent ("rafa, via blender-agent"). A write that
  cannot name a person is **refused**, never stored anonymously.
- **Agent authorship is visible** — anywhere a human reads annotations, an
  agent-authored one is marked as such. A person reviewing a thread never has to
  guess whether a machine wrote it.
- **Flood protection** — per-actor, per-asset rate limits and near-duplicate
  suppression, so a looping agent cannot bury a human thread under two hundred
  variations of the same sentence.
- **The prohibitions are restated as requirements, not assumed inherited** — no
  promotion tool, no constraint edit, no creating an asset, no creating a
  specification file.

## Capabilities

### New Capabilities

- `mcp-write-surface`: the complete write surface available to an automated
  caller — the two tools and the specified impossibility of a third, the identity
  and credential-acquisition rules that gate them, two-party attribution and the
  refusal of anonymous writes, observation semantics and visible agent authorship,
  non-blocking outcome reporting, and the flood protection that keeps a looping
  agent from drowning a human conversation.

### Modified Capabilities

None. No earlier change is archived yet, so a delta against an unarchived
capability cannot be written; requirements that touch the existing agent surface,
the command line and the annotation record are therefore specified inside
`mcp-write-surface` itself.

## Non-goals

Explicitly **not** in this change:

- **No promotion tool, and not for any role.** Not deferred, not gated behind an
  art director's credential — prohibited, and specified as prohibited.
- **No constraint, rule or budget editing by an automated caller**, in any tool,
  under any wording. An agent reports that a budget is unreachable; the budget does
  not move.
- **No asset creation and no specification-file creation by an agent.** An agent
  writes to assets that already exist and to nothing else.
- **No annotation resolution, no triage, no status changes, no approvals.** The
  two exits stay human. An agent cannot close its own observation either.
- **No third tool "while we are in here"** — no `update_spec`, no `set_status`,
  no `attach_view`, no `suggest_alias`. Acceptance of a suggestion is
  `add-derived-metadata`'s human action and stays one.
- **No hosted or multi-tenant MCP mode.** The server remains local stdio; writes
  change what it may do, not where it runs.
- **No new annotation anchoring machinery.** Anchors are what the viewer changes
  define; this change consumes them.
- **No notification, digest or mention system.** Who learns that an agent left an
  observation is the human surfaces' problem.
- **No agent-authored content in the compiled briefing beyond what triage already
  allows** — an open observation appears as an open issue, and a resolved one
  disappears, exactly like a human's.

## Impact

- **New code** — use cases `record_observation`, `report_validation_outcome`,
  `sign_in`, `sign_out`, `show_identity`; ports `CredentialStore`,
  `AnnotationWriter` and `OutcomeReporter` under
  `libs/cybercanon/application/ports/`; outbound adapters for the operating
  system's credential store, the device authorization flow, the annotation
  write-back and the local report outbox; two tools added to
  `libs/cybercanon/adapters/inbound/mcp/`.
- **Extended** — the domain gains observation kinds, agent authorship on an
  annotation and a rate-limit policy; `Attribution` from the read change gains a
  required agent slot on the write path; the exact-match tool-surface test from the
  read change grows by exactly two names, which is the point of it existing.
- **New dependency** — an operating system keyring client. No provider SDK, and no
  new transport: the device authorization flow is a documented HTTP exchange
  against CyberdyneAuth.
- **Configuration** — the agent client's launch entry gains an agent identifier;
  no secret ever appears in it. The credential lives in the keychain, and the
  report outbox is a git-ignored file under `.canon/`.
- **Consumer-side impact** — a person runs `canon login` once per machine. A game
  repository begins to see `asset.yaml` diffs whose annotation entries are marked
  agent-authored, reviewed and committed like any other change. Nothing about the
  validator's offline behaviour changes.
