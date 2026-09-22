-- Concept views (add-concept-ingestion D3): what each mirrored blob actually is.
--
-- The bytes live in blob storage under their content hash, which is what makes
-- mirroring idempotent, an identical image uploaded to two assets cost one
-- object, and orphan collection a set difference against the repository. What
-- that hash *is* — which asset, which slot, which revision — is this table.
--
-- Rebuildable by definition, like everything else in this schema: the rows are
-- reconstructed by walking the repository for `<asset dir>/concept/<slot>.<ext>`
-- files, so dropping the table costs a re-mirror and never an answer. A read
-- that finds no row falls back to the repository rather than reporting the view
-- as missing.
--
-- The key is (project, digest): two assets referencing identical bytes resolve
-- to one stored object, and the row says which view a given digest belongs to
-- within one project.

CREATE TABLE IF NOT EXISTS concept_views (
    project    text   NOT NULL,
    digest     text   NOT NULL,
    asset_id   text   NOT NULL,
    slot       text   NOT NULL,
    revision   text   NOT NULL,
    path       text   NOT NULL,
    byte_size  bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (project, digest)
);

CREATE INDEX IF NOT EXISTS concept_views_by_asset ON concept_views (project, asset_id, slot);
