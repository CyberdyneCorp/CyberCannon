-- Dismissals (D9): which unread item each person has already looked at.
--
-- The one deliberate exception to "the index holds nothing durable", and it is
-- recorded rather than discovered: *"The state that must survive an index
-- rebuild — the request, its assignee, its state, its attribution — is
-- repository content; the state that may be lost is whether someone has already
-- looked at it."* After a rebuild, previously dismissed items reappear as
-- unread. The cost is one person clicking dismiss again; the alternative is a
-- commit per glance.
--
-- The key is (project, actor, subject) because `asset-requests` requires
-- dismissal to be per person: one of two people dismissing an item leaves it
-- unread for the other, which is only true if the recipient is part of the key.

CREATE TABLE IF NOT EXISTS dismissals (
    project      text        NOT NULL,
    actor        text        NOT NULL,
    subject      text        NOT NULL,
    dismissed_at timestamptz NOT NULL,
    PRIMARY KEY (project, actor, subject)
);

CREATE INDEX IF NOT EXISTS dismissals_by_actor ON dismissals (actor, project);
