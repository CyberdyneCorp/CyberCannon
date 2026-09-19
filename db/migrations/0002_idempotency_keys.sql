-- Idempotency keys (D11): the request a key was first used for, and the answer
-- it got, kept for a bounded period.
--
-- This is index state on purpose and its loss is survivable on purpose: *"the
-- record lives in the index, so an index rebuild forgets it and a very late
-- retry could apply twice. It cannot, in practice, because D5's per-file
-- precondition refuses the second apply."* Idempotency makes the retry quiet;
-- the content hash makes it safe.
--
-- `request_digest` is the digest of the request body, so a replay carrying a
-- different body under the same key is refused rather than served somebody
-- else's answer. `payload` is the surface's own rendering of a successful
-- value, stored verbatim, because a replay has to return *the original
-- outcome* and re-deriving it would be running the operation again.

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key            text        PRIMARY KEY,
    request_digest text        NOT NULL,
    kind           text,
    identifier     text        NOT NULL,
    message        text        NOT NULL DEFAULT '',
    subject        text        NOT NULL DEFAULT '',
    payload        text        NOT NULL DEFAULT '',
    stored_at      timestamptz NOT NULL,
    expires_at     timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idempotency_keys_expiry ON idempotency_keys (expires_at);
