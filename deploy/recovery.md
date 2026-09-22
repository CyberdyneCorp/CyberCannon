# Recovery — the runbook, the expected durations, and the drill log

Three pieces of CyberCanon's hosted state live on volumes, and **every one of
them is derived**. Git is the source of truth; PostgreSQL is a rebuildable index
and MinIO is a blob mirror. So losing a volume is not an incident to be restored
from — it is a procedure to be run, and this is the page you run it from.

> **There is no backup of the index and no backup of the blob mirror, and there
> will not be one (D5).** A restore path would make the index authoritative in
> practice even while `openspec/project.md` says it is not: the first time
> somebody chooses a restore over a rebuild, the rebuild path rots and the claim
> quietly stops being true. The cost accepted is that recovery time scales with
> the repository rather than being constant — which is why every procedure below
> carries a duration that was **measured**, and why a drill whose duration
> exceeds it fails the build.

`../docs/recovery.md` is the neighbouring page and answers a different question:
*what state does this service hold, and is all of it rebuildable?* That is
`add-web-backend`'s property. This page is `deployment-operations`': *how does an
operator get a lost volume back, how long will it take, and when did anybody
last check?*

## The three procedures

Each recovers one volume. The last column is what it is expected to take, and it
is the number the drill log below is checked against.

| Procedure | Volume | Recovers from | Expected |
|---|---|---|---|
| `working-copy-re-clone` | `/data/worktrees/<project>` | the git host | `10m` |
| `index-rebuild` | the `postgres` application's data directory | the working copy | `30m` |
| `blob-re-mirror` | the `minio` application's data directory | the working copy | `45m` |

**They are ordered, and the order is not a preference.** The working copy is
what the other two read, so a lost working copy is re-cloned first; rebuilding
an index from a copy that is not there yet measures an error path rather than a
recovery. The two derived procedures are independent of each other and are per
project, so a deployment with several projects recovers project by project
rather than all at once.

### `working-copy-re-clone`

The volume under `/data/worktrees/<project>` is gone, or holds a copy that
diverged from the configured branch.

The working copy is re-obtained by the service itself: the repository host
clones a copy that is missing and resets one that diverged, **reporting every
local commit it discarded** rather than resolving toward the remote in silence.
Restarting the `api` application is therefore the whole procedure — the boot
step returns every project's working copy to its configured branch, which is
also what makes an instance killed mid-write-back leave nothing half-applied
behind it. A copy that is still missing is re-cloned by the first read.

While it runs, that project's reads report `provisioning` rather than answering
an empty asset list, and `/status` shows the project recovering.

**Confirm it worked:** `/status` reports a revision and a fetch time for the
project, and the revision is the configured branch's current one.

### `index-rebuild`

The index volume is gone, or the schema is in a state no migration can advance.
The procedure is `drop → migrate → rebuild`, and it is one command:

```
python -m cybercanon.api.recover /data/worktrees/<project>
```

It discards every table the migration set creates, applies the set to the target
version, and rebuilds the index from the working copy through the same
`rebuild_index` use case the command line and the hosted service call — there is
no second implementation of an index rebuild, and a recovery that used one would
recover a different index from the one it lost. It prints its progress as it
goes, so a long rebuild is visibly a rebuild and not a hang, and it is resumable.

While it runs, `/status` reports the rebuild as in progress and reads that
cannot be served from the partial index report unavailability rather than an
incomplete answer. Reads the working copy alone can answer keep answering.

**Confirm it worked:** lookups return what they returned before the loss, and
`/status` reports the index in sync with the working-copy revision.

### `blob-re-mirror`

The blob volume is gone. Every blob the mirror holds is derived from a file the
repository has, so the mirror is re-derived from the working copy.

Because a blob's key is the digest of its content, **every object lands under
the key it had before**. Links, references and compiled specifications that
predate the loss keep resolving, and that is a property of content addressing
rather than of bookkeeping that survived.

**Confirm it worked:** every reference recorded before the loss retrieves the
same bytes.

## Drills: run, not assumed

A procedure nobody has executed since it was written is a hope with formatting,
so a **scheduled job runs all three against pre-production every 7 days**,
destroying the volume first so the procedure meets a real loss, measuring only
the recovery, and appending its own record below (D9).

```
just drill --project <project> --working-copy /data/worktrees/<project> --blobs /data/blobs
just drill-check
```

`just drill-check` is the gate. It fails when a procedure has never been
drilled, when its most recent drill is older than the 7-day interval, or when
that drill took longer than the expected duration above. The last of those is
the one worth reading twice: **a drill that overran is the signal to change the
architecture, not the signal to add backups.**

It runs in the **release pipeline and as the drill job's own exit code**, and
deliberately not inside `just check`: staleness is a function of today's date
rather than of the change under review, so a build that ran it would start
failing on a Tuesday for a repository nobody had touched — and a check that
fails for reasons unrelated to the change is a check people learn to ignore.
What `just check` asserts instead is everything about this page that *is* a
function of the repository: that all three procedures are documented, that each
states an expected duration, that each carries a dated, measured record, that no
procedure mentions a backup or a restore, and that every recorded duration is
within its expectation (`tests/tooling/test_recovery_document.py`).

The durations recorded against `developer` are a floor rather than an estimate
for a studio repository — they come from the suite that runs all three against
real git, a real PostgreSQL and a real S3 API on one fixture project, and they
exist so that a regression in the *procedure* is visible. The number an on-call
engineer plans around is the pre-production one.

## Drill log

Appended by the drill itself, oldest first. Nobody edits this table by hand.

| Date | Procedure | Measured | Environment |
|---|---|---|---|
| 2026-09-22 | working-copy-re-clone | 0.11s | developer |
| 2026-09-22 | index-rebuild | 0.04s | developer |
| 2026-09-22 | blob-re-mirror | 0.18s | developer |
