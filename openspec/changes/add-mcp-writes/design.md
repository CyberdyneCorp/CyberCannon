# Design

## Context

Change 2 built the read surface and, in its D5 and D6, laid two foundations for
this one: `Attribution(actor, via)` with a non-optional actor, and an exact-match
test over the advertised tool names. This change is where both are cashed in — it
adds the first tools that record state, and it is the first part of CyberCanon
that needs a credential at all.

The governing constraint from `openspec/project.md` is unchanged and is the reason
this change is sixth rather than second: **agents read constraints, agents never
write constraints.** Everything below is arranged so that the prohibition is a
property of the structure rather than a rule someone remembers.

One boundary is worth stating up front, because it decides half the design. There
are two possible destinations for a write — the local git working copy the agent's
human is working in, and the hosted API that serves the web surface. Building both
would produce two behaviours for one tool, which is the drift this project
repeatedly refuses. See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**

- Make a third write tool require editing a list and defending it in review.
- Make an anonymous write impossible to construct, not merely rejected.
- Keep the read surface identity-free after writes exist, including under an
  identity outage.
- Keep the validation verdict local, offline and authoritative, with reporting as
  an unreliable side channel by design.
- Give a human reviewer an ordinary, reviewable diff for anything an agent wrote.

**Non-Goals (design level):**

- No queue, broker or background daemon. The retry mechanism is a file and an
  opportunistic flush.
- No distributed rate limiting. One machine, one server process.
- No conflict-resolution strategy for concurrent annotation writes beyond
  re-reading the file. Two agents annotating the same asset in the same second is
  not a real scenario at this scale.
- No token introspection, scopes or audience validation logic in this change — the
  identity adapter owns that, exactly as change 2 decided.

## Decisions

### D1 — One use case per tool, one outbound port per destination, and the composition root picks the destination

`record_observation` and `report_validation_outcome` are application use cases
behind two new ports: `AnnotationWriter` (append an annotation to an asset) and
`OutcomeReporter` (deliver a verdict). The local MCP server wires
`AnnotationWriter` to the git working copy and `OutcomeReporter` to the local
outbox; the hosted API wires the same ports to its own implementations when
`add-web-backend` lands.

*Why:* the tool must behave identically whether the person is working locally or
through the hosted surface, and the only way that survives contact with two
deployments is for the difference to live in the composition root. **Alternative
rejected:** the MCP tool choosing its destination at call time based on whether a
server is configured — two code paths through one tool, which is precisely how
"it worked locally but the site disagrees" gets built. **Cost accepted:** the
hosted implementations of both ports are specified here but written in
`add-web-backend`; until then the ports have exactly one adapter each, which looks
like over-abstraction and is not.

### D2 — A local annotation write modifies the working copy and does not commit

`GitAnnotationWriter` appends the entry to the `annotations` block of the asset's
specification file in the working copy, preserving comments and formatting, and
stops there. It does not stage, commit, branch or push. The tool response says
which file changed and that it is uncommitted.

*Why:* git is the source of truth, and the human review of a diff is the thing that
keeps an agent's contribution accountable. An auto-commit would write into an
artist's working tree mid-edit, could land during a rebase, and would turn a
proposal into a fait accompli. **Alternative rejected:** committing on a dedicated
branch — it needs branch management, conflicts with the artist's current branch,
and the resulting commits are invisible in the branch they actually matter in.
**Cost accepted:** an observation can be destroyed by `git checkout .` before
anyone reads it. Mitigated by saying so in the response; not mitigated further,
because the alternative costs more.

*Note on the hosted path:* the hosted `AnnotationWriter` is the one place a direct
commit is correct, because there is no human working tree to disturb — that is
`add-web-backend`'s resolved persistent-working-copy decision, and this change
does not restate it.

### D3 — The write tools extend change 2's exact-match tool test rather than escaping it

The expected tool-name list grows by exactly two entries. The "clean working tree"
assertion from change 2's D6 is refined rather than dropped: **every read tool
leaves the tree clean, and a write tool's only permitted change is the annotations
block of the asset it named.** A test asserts precisely that, by diffing the tree
after a write and rejecting any other path or any other block.

*Why:* an absence cannot be enforced by absence, and a weakened test is how a
guarantee quietly dies. Refining the assertion keeps it as sharp as it was.
**Alternative rejected:** exempting write tools from the tree check, which would
leave nothing enforcing "an agent may not create a specification file."

### D4 — Attribution gains a required `via`, and the agent identifier comes from launch configuration

The write path takes `Attribution(actor, via)` where `via` is non-optional; the
domain exposes no constructor for a write attribution without both slots. The
`AgentId` is read from the server's launch arguments or environment — the same
trust class as the credential — and never from a tool parameter or the annotation
text. A server started without one serves reads and refuses writes.

*Why:* the spec requires an unattributable write to be refused rather than recorded
anonymously. Making both slots non-optional means the anonymous record is not
constructible, so the refusal cannot be forgotten at one call site. Sourcing the
agent identifier from launch configuration keeps it consistent with change 2's rule
that identity is never a parameter. **Alternative rejected:** defaulting a missing
agent identifier to `unknown-agent`, which is exactly the anonymous record the
spec forbids, wearing a name.

### D5 — The credential is a port with one keychain adapter, and sign-in is a CLI action only

`CredentialStore` (get, set, clear) is backed by the operating system's credential
store; `DeviceAuthorizationFlow` performs the device-code exchange. `canon login`,
`canon logout` and `canon whoami` are the only entry points. The MCP server reads
the stored credential and refreshes it; it never initiates a flow.

*Why:* a device-code flow needs a human at a browser, and an MCP tool call has no
way to get one — a tool that blocks for two minutes waiting for a person to click
is worse than a refusal naming `canon login`. Putting the credential behind a port
also keeps the domain innocent of tokens, as change 2 required. **Alternative
rejected:** a static API token in an environment variable — it ends up pasted into
agent client configurations, never rotates, and attributes to a machine rather than
a person, which breaks the attribution the whole change exists to provide. **Cost
accepted:** a keyring dependency and a per-platform failure mode; when the keychain
is unavailable the system reports that writes are unavailable and keeps reads
working, rather than falling back to a file.

### D6 — `report_export` writes to a local outbox and flushes opportunistically

The tool appends the outcome to a git-ignored newline-delimited file under
`.canon/`, attempts a delivery, and returns success either way. Delivery is retried
on the next report and by `canon report flush`. The tool never awaits network
success.

*Why:* the spec requires that a reporting failure never blocks a commit, a
validation or the agent. The only way to guarantee that is for the tool's success
not to depend on delivery at all. **Alternative rejected:** synchronous delivery
with a retry budget inside the call — it makes an agent's latency a function of a
server's health, and a pre-commit hook would eventually inherit that. **Deferred:**
a background flush daemon; opportunistic flushing is enough while the reports are
telemetry. **Cost accepted:** outcomes can be permanently lost with the machine.
Acceptable precisely because the verdict is authoritative locally and the report is
not canon — if it ever became the basis for a gate, this decision must be revisited.

### D7 — An outcome's identity is (asset, export content hash, verdict hash)

The outbox and the destination both key on that triple; re-delivering a retained
report replaces the record rather than appending one. A re-export changes the
export hash, producing a new, distinguishable outcome.

*Why:* retries are the normal case in D6, so idempotency is a precondition rather
than a refinement, and keying on content means it holds without a client-generated
identifier that a restarted agent would lose. **Alternative rejected:**
deduplication at the destination only, which leaves the outbox itself growing
copies and makes the local `canon report flush` output misleading.

### D8 — An observation is an ordinary annotation with an author kind, not a parallel record type

The domain's annotation entry gains `author_kind: human | agent` and `kind` from a
closed `ObservationKind` enumeration (`unattainable_constraint`, `ambiguity`,
`defect`). Everything else — anchors, open/resolved state, triage, compilation — is
reused unchanged.

*Why:* the two-exit discipline is the mechanism that keeps the compiled briefing
from rotting, and a parallel "agent reports" collection would need its own triage,
its own rendering and its own way of going stale. One record type means an agent's
observation is reviewed by the same person doing the same pass. **Alternative
rejected:** a separate collection with a promotion path into annotations, which is
the same work twice plus a migration between them. **Cost accepted:** every
annotation reader must now render the author kind, which is why the spec requires
the marking on every human surface rather than leaving it to each view.

### D9 — Rate limiting is a domain policy over recorded history, with an in-process counter in front

`WritePolicy` is a pure function over the actor, the asset, the observations
already recorded and a clock; the server keeps an in-process token bucket per
`(actor, asset)` as a cheap first gate. Reporting has its own separate bucket.

*Why:* a purely in-process limiter resets when a looping agent crashes and restarts
— which is the exact failure being defended against — so the durable protection has
to be derived from what is already recorded. A pure policy function also makes the
limits testable with a fake clock and no server. **Alternative rejected:** a single
global per-process limit, which throttles an agent's work on asset B because of its
loop on asset A. **Cost accepted:** the policy reads recent annotations on each
write, which is a file read the in-process bucket usually short-circuits.

### D10 — Near-duplicate suppression compares against open observations from the same agent only

Materially-same is defined as: same asset, same target, same kind, same agent, and
normalised text (case-folded, whitespace-collapsed, punctuation-stripped) equal to
an existing **open** observation. A resolved one does not suppress.

*Why:* the goal is one thread per issue, not censorship of a recurring problem. If a
person resolved an observation and the agent still hits it, that is new information
and must be recordable. Restricting the comparison to the same agent avoids one
agent silently swallowing another's finding. **Alternative rejected:** fuzzy
similarity scoring, which needs a threshold nobody can justify and would eventually
drop a distinct observation. **Cost accepted:** two rephrasings of the same problem
create two threads; the rate limit bounds the damage.

## Risks / Trade-offs

- **The third tool arrives in six months, reasonably argued** → D3's exact-match
  list plus the refined tree assertion; adding one means editing a test named for
  the prohibition and explaining it in review.
- **An agent's observation is lost to a discarded working tree** (D2) → The tool
  response names the modified file and says it is uncommitted; the read surface
  reports uncommitted agent observations so the next human read surfaces them.
- **Annotation noise makes triage worse rather than better** → D9 and D10 bound the
  volume, the author-kind marking lets a director filter agent observations, and
  the acceptance task measures triage load before and after.
- **A write lands while the artist is mid-rebase and the file is in conflict** →
  The writer refuses on an unmergeable or conflicted file, reports the condition,
  and the outbox does not apply to annotations; the agent is told to retry.
- **The keychain is unavailable on a locked-down machine** (D5) → Writes report as
  unavailable with the reason; reads are untouched, which is the degradation the
  spec already requires for a missing identity.
- **Reports silently stop arriving and nobody notices** (D6) → `canon whoami` and
  `canon report flush` both report the pending count; a growing outbox is visible
  where a person already looks.
- **Two-party attribution is only as good as the identity mapping** → The actor
  mapping in `.canon/actors.yaml` from change 2 is what binds the authenticated
  subject to the git author; a write by an unmapped subject is recorded with the
  subject and flagged unmapped rather than guessed.

## Migration Plan

Additive, and off by default in the strongest sense: a machine that never runs
`canon login` sees no change at all, because writes refuse without a credential and
every read path is untouched. Agent clients gain an agent identifier in their
launch entry; a client without one keeps the full read surface. The outbox file is
git-ignored. Rollback is removing the two tools from the advertised list — no
repository content and no stored credential needs undoing, and observations already
written are ordinary annotations that survive the rollback as human-reviewable
entries.

## Open Questions

- **Whether an agent observation should be readable as "uncommitted" through the
  read surface**, or whether the working-tree state is the human's business alone.
  This adds a field to a response and changes no specification.
- **The observation rate limit's numbers.** The limit is specified; the values are
  configuration, and the first real Blender-agent session is what sets them.
- **Whether `ObservationKind` needs a fourth member for "export tooling failed"**,
  which is arguably an outcome report rather than an observation. Deferred until a
  real case appears; adding a member does not change any requirement.
