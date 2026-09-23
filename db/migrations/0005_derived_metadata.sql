-- Derived metadata (add-derived-metadata, D5 and D6): proposals, never canon.
--
-- Generated descriptions, tags and suggested aliases live here and nowhere
-- else. `project.md`: *"derived content lives in the rebuildable index keyed by
-- the blob's content hash — never in `asset.yaml`, never in the compiled
-- `art-spec.md`"*. Two tables, and each primary key is one of the change's
-- numbered decisions written where the database enforces it:
--
--   * `derived_records` is keyed by (project, source_hash) — **D5**. Not by
--     asset and not by path: renaming a view, moving an asset or dropping the
--     same image into two assets all resolve to one record, regenerating an
--     unchanged image lands on the row that is already there, and a replaced
--     image can never inherit the description of the one before it.
--   * `suggestion_decisions` is keyed by (project, source_hash, value) — **D6**.
--     A rejected term stays rejected *for that image*: regenerating produces
--     the same suggestions and the rejection still applies. Keyed by the asset,
--     every rebuild would resurrect rejections the team had already worked
--     through.
--
-- Both are disposable in the strong sense the specification asks for: deleting
-- every row here loses no project information at all, because an accepted value
-- is not here — it is an ordinary alias in an `asset.yaml`, authored by the
-- person who accepted it, and indistinguishable from one they typed.
--
-- Nothing here feeds `assets.searchable` or the `tsvector`. A suggestion
-- reaches the ranked cascade only through its sixth and lowest-priority pass,
-- joined at query time, so there is no path by which a generated term could
-- start matching as though a person had written it.

CREATE TABLE IF NOT EXISTS derived_records (
    project           text NOT NULL,
    source_hash       text NOT NULL,
    asset_id          text NOT NULL DEFAULT '',
    source_path       text NOT NULL DEFAULT '',
    model             text NOT NULL DEFAULT '',
    generated_at      text NOT NULL DEFAULT '',
    description       text NOT NULL DEFAULT '',
    tags              text NOT NULL DEFAULT '',
    suggested_aliases text NOT NULL DEFAULT '',
    PRIMARY KEY (project, source_hash)
);

CREATE INDEX IF NOT EXISTS derived_records_by_asset ON derived_records (project, asset_id);

CREATE TABLE IF NOT EXISTS suggestion_decisions (
    project     text NOT NULL,
    source_hash text NOT NULL,
    value       text NOT NULL,
    state       text NOT NULL,
    actor       text NOT NULL DEFAULT '',
    decided_at  text NOT NULL DEFAULT '',
    written     text NOT NULL DEFAULT '',
    PRIMARY KEY (project, source_hash, value)
);
