-- The rebuildable index: one row per asset, plus the text a search narrows on.
--
-- Everything here is derived. Git is the source of truth (openspec/project.md),
-- so dropping this schema and running the rebuild is always a complete
-- recovery, and nothing in it is the place a fact originates. That is why there
-- is no sequence, no audit column and no soft delete: a row is a projection of
-- an `asset.yaml`, and the way to correct one is to re-read the file.
--
-- `searchable` and `tags_key` are normalised copies of values that are already
-- stored verbatim beside them. They carry no information; they are the
-- lower-cased forms a filter and the substring pass compare against, so a row
-- still reads back exactly as it was written.
--
-- `document` is the full-text vector the ordinary token query uses. It narrows;
-- it never ranks. Ranking is the cascade in
-- `cybercanon.application.ports.search_index.rank`, which every implementation
-- sorts with (D9) — a `ts_rank` here would be a second search engine, and the
-- conformance suite would be the only thing that noticed.

CREATE TABLE IF NOT EXISTS assets (
    project              text    NOT NULL,
    asset_id             text    NOT NULL,
    name                 text    NOT NULL DEFAULT '',
    status               text,
    aliases              text    NOT NULL DEFAULT '',
    tags                 text    NOT NULL DEFAULT '',
    description          text    NOT NULL DEFAULT '',
    spec_path            text    NOT NULL DEFAULT '',
    directory            text    NOT NULL DEFAULT '',
    source_file          text,
    engine_path          text,
    discussion           text,
    design_doc           text,
    owner_art            text,
    owner_design         text,
    owner_code           text,
    validated_export     text,
    validated_at         text,
    fingerprint_path     text,
    fingerprint_size     bigint,
    fingerprint_mtime_ns bigint,
    tags_key             text    NOT NULL DEFAULT '',
    searchable           text    NOT NULL DEFAULT '',
    document             tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(searchable, ''))
    ) STORED,
    PRIMARY KEY (project, asset_id)
);

CREATE INDEX IF NOT EXISTS assets_document ON assets USING gin (document);
CREATE INDEX IF NOT EXISTS assets_by_id ON assets (asset_id);

-- Zero-result search terms (D11). Counted rather than appended: the question
-- they answer is *which term do people keep asking for*, and a list with the
-- same word forty times answers it worse than a count does. Never transmitted
-- anywhere; a person reads it and decides which aliases to add.
CREATE TABLE IF NOT EXISTS search_misses (
    project  text    NOT NULL,
    term_key text    NOT NULL,
    term     text    NOT NULL,
    count    bigint  NOT NULL DEFAULT 1,
    PRIMARY KEY (project, term_key)
);
