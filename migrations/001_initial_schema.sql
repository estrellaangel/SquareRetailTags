-- Square catalog mirror
CREATE TABLE catalog_items (
    id          TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE catalog_variations (
    id              TEXT        PRIMARY KEY,
    item_id         TEXT        NOT NULL REFERENCES catalog_items (id) ON DELETE CASCADE,
    variation_name  TEXT        NOT NULL,
    sku             TEXT,
    -- Integer cents. NULL when pricing_type = 'VARIABLE_PRICING'.
    price           INTEGER,
    pricing_type    TEXT        NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX catalog_variations_item_id ON catalog_variations (item_id);

-- Opaque Square cursor for delta sync.
-- latest_time is the value returned by SearchCatalogObjects, passed as
-- begin_time on the next run. Stored as TEXT because it is an opaque string,
-- not a wall-clock timestamp we control.
CREATE TABLE sync_cursors (
    id          TEXT PRIMARY KEY,
    latest_time TEXT NOT NULL
);

-- ESL tag desired state
CREATE TABLE tags (
    id                CHAR(16)    PRIMARY KEY,  -- 16-char uppercase hex, normalized at API boundary
    variation_id      TEXT        REFERENCES catalog_variations (id) ON DELETE SET NULL,
    content_hash      TEXT,
    last_pushed_at    TIMESTAMPTZ,
    last_confirmed_at TIMESTAMPTZ,
    battery_pct       SMALLINT
);
