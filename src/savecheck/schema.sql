-- SaveCheck price store — raw DDL mirroring src/savecheck/models.py.
-- Use this for a quick bootstrap; switch to Alembic migrations as the schema grows.

CREATE TABLE IF NOT EXISTS chain (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS store (
    id          SERIAL PRIMARY KEY,
    chain_id    INTEGER NOT NULL REFERENCES chain(id) ON DELETE CASCADE,
    external_id VARCHAR(120),
    region      VARCHAR(120),
    address     VARCHAR(255),
    UNIQUE (chain_id, external_id)
);

CREATE TABLE IF NOT EXISTS product (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(255) NOT NULL,
    category     VARCHAR(120),
    brand        VARCHAR(120),
    package_size VARCHAR(60),
    basket_group VARCHAR(60)
);

CREATE TABLE IF NOT EXISTS chain_product (
    id          SERIAL PRIMARY KEY,
    chain_id    INTEGER NOT NULL REFERENCES chain(id) ON DELETE CASCADE,
    product_id  INTEGER REFERENCES product(id) ON DELETE SET NULL,
    external_id VARCHAR(120),
    raw_name    VARCHAR(255) NOT NULL,
    UNIQUE (chain_id, external_id)
);

CREATE TABLE IF NOT EXISTS price_observation (
    id               SERIAL PRIMARY KEY,
    chain_product_id INTEGER NOT NULL REFERENCES chain_product(id) ON DELETE CASCADE,
    store_id         INTEGER REFERENCES store(id) ON DELETE SET NULL,
    observed_on      DATE NOT NULL,
    price            NUMERIC(10, 2) NOT NULL,
    is_promo         BOOLEAN NOT NULL DEFAULT FALSE,
    source           VARCHAR(60) NOT NULL DEFAULT 'kolkostruva',
    ingested_at      TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (chain_product_id, store_id, observed_on, source)
);

CREATE TABLE IF NOT EXISTS watch (
    id                   SERIAL PRIMARY KEY,
    user_id              VARCHAR(120) NOT NULL,
    chain_product_id     INTEGER NOT NULL REFERENCES chain_product(id) ON DELETE CASCADE,
    target_price         NUMERIC(10, 2),
    notify_on_real_promo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, chain_product_id)
);

-- The pricing core queries observations by product and day window, so index for it.
CREATE INDEX IF NOT EXISTS ix_obs_cp_day ON price_observation (chain_product_id, observed_on);
CREATE INDEX IF NOT EXISTS ix_obs_day ON price_observation (observed_on);
CREATE INDEX IF NOT EXISTS ix_watch_product ON watch (chain_product_id);
