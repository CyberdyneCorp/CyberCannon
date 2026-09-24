# Proposal

## Why

Every signed-in person saw *"Your credential carries no git identity"*, with
five repository actions listed as unavailable. That included the one person
mapped in the served project's `.canon/actors.yaml`, who could in fact write.

The frame decides whether to warn from a `git_emails` claim, and CyberdyneAuth
emits no such claim (checked against a real production token). So the warning
fired for 100% of sessions, and its advice ("until one is recorded … in
`.canon/actors.yaml`") pointed at a file that already had the entry.

"The credential says nothing" was being read as "the person is unmapped". The
first is *not evaluated*; the second is *violated*. This product is built on
not mixing those two up.

## What Changes

- An identity's git mapping has three states: `mapped` (the credential names a
  git email), `unmapped` (the credential carries the claim, and it names
  nobody), and `unknown` (the credential carries no such claim).
- The early warning is shown only for `unmapped`. An `unknown` mapping shows
  nothing. If the person really is unmapped, the domain's refusal still names
  the missing `.canon/actors.yaml` entry.

## Impact

- Affected capability: `web-session` (the early warning for an unmapped person).
- Affected code: `apps/cybercanon/web/src/lib/session/identity.ts`.
- Not changed: a credential that does carry `git_emails` behaves exactly as
  before. Warning a file-mapped person *before* a write needs an `http-api`
  endpoint that states whether the acting person is mapped. That is a gap in
  `http-api`, not work for this change.
