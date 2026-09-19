# Recovery — losing the working copy, the index and the blob store

Git is the source of truth. PostgreSQL is a **rebuildable index** and MinIO is a
**blob mirror**, which is a claim about what happens when all three are
destroyed — so this is the procedure that destroys them, and the drill that runs
it on every build.

> **The drill is `tests/integration/test_recovery_and_concurrency_drills.py`**
> (task 11.4 of `add-web-backend`). It records every answer a project gives,
> deletes the working copy, empties the object store, drops the schema, restarts
> from the remote alone, and asserts that every answer comes back identical —
> blobs included, **under the same keys**.

## What is recoverable, and from what

| State | Lives on | Recovered from | Lost |
|---|---|---|---|
| Specifications, actors mapping, asset requests | the working copy | the remote repository | nothing |
| Asset index, search, lookups | PostgreSQL | a rebuild over the working copy | nothing |
| Views, exports, preview meshes | the object store | a re-mirror over the working copy | nothing |
| Idempotency keys | PostgreSQL | nothing — they expire anyway | a replayed write becomes a fresh one, which D5's per-file precondition then refuses |
| Notification dismissals | PostgreSQL | nothing | previously dismissed items reappear as unread (D9, stated and accepted) |

Nothing else is held. A request is repository content (D7), which is why the
drill can assert that its state, its assignee and its attribution survive a
database that no longer exists.

## The procedure

1. **Apply the migration set** — `just migrate`. It is the release step, it is
   idempotent, and it recreates the schema the rebuild will populate.
2. **Re-obtain the working copy** — the repository host's `recover`, which
   re-clones a missing copy and resets a diverged one, reporting any local
   commits it discarded. Reads report `provisioning` until it finishes rather
   than answering an empty asset list.
3. **Rebuild the index** — per project, over the working copy. Reads that the
   index would have answered fall back to the working copy while it runs.
4. **Re-mirror the blobs** — per project, over the same working copy. Because
   keys are content digests, every object lands under the key it had before, so
   links and references that predate the loss keep resolving.

Steps 2 to 4 are per project and independent, so a large deployment recovers
project by project rather than all at once.

## How long it takes

The drill measures the wall-clock time of steps 1 to 4 and prints it:

```
recovery drill: 0.56s for 3 blobs
```

That is the fixture project — two assets, four blobs behind three keys, two
requests — on a developer machine, and it is a **floor, not an estimate for a
studio repository**: the cost is dominated by the clone and by the number of
blobs, both of which scale with the repository rather than with anything this
service holds. Re-run the drill against a real project before quoting a number
in an operational document; the figure above exists so that a regression in the
procedure is visible, not so that an on-call engineer can plan around it.

## What this document is not

Container orchestration, health gating during a rebuild, volume provisioning and
the runbook an on-call engineer follows belong to `add-coolify-deployment`
(`deployment-operations`). This page is the property `add-web-backend` owns:
**every piece of state this service holds is rebuildable from the remote, and
the drill proves it.**
