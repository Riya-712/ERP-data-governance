-- =========================================================
-- Phase 5 (SQL half): Load cleaned data into `staging` tables.
-- Run AFTER python/04_standardize_enrich.py has written the
-- governance/staging_*.csv files.
--
-- Two ways to load these CSVs into Postgres:
--   (a) psql's \copy meta-command (below), run from the psql prompt
--       or via `psql -f` -- easiest if you're already in a terminal.
--   (b) pandas .to_sql() from Python -- easier if you want it to
--       happen automatically at the end of 04_standardize_enrich.py.
-- Either is fine for a portfolio project; (a) is shown here since
-- it keeps the SQL/Python split visible for your write-up.
-- =========================================================

DROP TABLE IF EXISTS staging.products;
CREATE TABLE staging.products (
    sku            TEXT PRIMARY KEY,
    product_name   TEXT,
    category       TEXT,
    price          NUMERIC,
    supplier_id    TEXT
);

DROP TABLE IF EXISTS staging.purchase_orders;
CREATE TABLE staging.purchase_orders (
    purchase_order_id        TEXT PRIMARY KEY,
    supplier_id               TEXT,
    sku                        TEXT,
    qty_ordered                 NUMERIC,
    order_date                   DATE,
    expected_delivery_date        DATE,
    delivery_status                 TEXT
);

DROP TABLE IF EXISTS staging.inventory;
CREATE TABLE staging.inventory (
    sku            TEXT,
    warehouse_id   TEXT,
    current_stock  NUMERIC,
    safety_stock   NUMERIC,
    last_updated   DATE
);

-- Run this from a terminal (adjust the path to wherever your governance/
-- folder actually is):
--
--   psql -d erp_governance -c "\copy staging.products FROM 'governance/staging_products.csv' WITH (FORMAT csv, HEADER true, NULL '')"
--   psql -d erp_governance -c "\copy staging.purchase_orders FROM 'governance/staging_purchase_orders.csv' WITH (FORMAT csv, HEADER true, NULL '')"
--   psql -d erp_governance -c "\copy staging.inventory FROM 'governance/staging_inventory.csv' WITH (FORMAT csv, HEADER true, NULL '')"
--
-- NOTE: your Python output CSVs have more columns than the staging table
-- (e.g. products.csv still has the original `category`/`sku`/`price` next
-- to the `_clean` versions, for audit purposes). \copy expects an exact
-- column match, so either:
--   1. Trim the CSV down to just the final columns before loading
--      (easiest: df[['sku_clean','product_name','category_clean',
--      'price_clean','supplier_id']].to_csv(...) at the end of the
--      Python script instead of the full audit dataframe), or
--   2. Load into a wide staging_raw table first, then
--      INSERT INTO staging.products SELECT sku_clean, product_name,
--      category_clean, price_clean, supplier_id FROM staging_raw;
-- Option 1 is cleaner -- worth changing the last few lines of
-- 04_standardize_enrich.py to write a "final" narrow CSV alongside
-- the wide audit CSV.