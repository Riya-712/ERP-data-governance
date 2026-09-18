-- =========================================================
-- Phase 1: Schema Setup
-- Run this once, connected to your target database
-- (e.g. `psql -d erp_governance -f sql/01_schema.sql`
--  or via the VS Code PostgreSQL extension's "Run Query" on this file)
-- =========================================================

-- Three schemas = three stages of the pipeline
CREATE SCHEMA IF NOT EXISTS raw;         -- CSVs loaded as-is, mess intact
CREATE SCHEMA IF NOT EXISTS staging;     -- cleaned / standardized versions
CREATE SCHEMA IF NOT EXISTS governance;  -- rule outputs, violations, scorecard

-- ---------------------------------------------------------
-- raw.products
-- ---------------------------------------------------------
DROP TABLE IF EXISTS raw.products;
CREATE TABLE raw.products (
    sku           TEXT,
    product_name  TEXT,
    category      TEXT,
    price         TEXT,   -- keep as TEXT at raw layer; some values may be dirty
    supplier_id   TEXT
);

-- ---------------------------------------------------------
-- raw.suppliers
-- ---------------------------------------------------------
DROP TABLE IF EXISTS raw.suppliers;
CREATE TABLE raw.suppliers (
    supplier_id        TEXT,
    name                TEXT,
    lead_time_days      TEXT,
    reliability_score   TEXT
);

-- ---------------------------------------------------------
-- raw.inventory
-- ---------------------------------------------------------
DROP TABLE IF EXISTS raw.inventory;
CREATE TABLE raw.inventory (
    sku            TEXT,
    warehouse_id   TEXT,
    current_stock  TEXT,
    safety_stock   TEXT,
    last_updated   TEXT
);

-- ---------------------------------------------------------
-- raw.inventory_transactions
-- ---------------------------------------------------------
DROP TABLE IF EXISTS raw.inventory_transactions;
CREATE TABLE raw.inventory_transactions (
    transaction_id     TEXT,
    sku                TEXT,
    warehouse_id       TEXT,
    transaction_type   TEXT,
    quantity_change    TEXT,
    timestamp          TEXT
);

-- ---------------------------------------------------------
-- raw.purchase_orders
-- ---------------------------------------------------------
DROP TABLE IF EXISTS raw.purchase_orders;
CREATE TABLE raw.purchase_orders (
    purchase_order_id       TEXT,
    supplier_id              TEXT,
    sku                       TEXT,
    qty_ordered               TEXT,
    order_date                TEXT,
    expected_delivery_date    TEXT,
    delivery_status            TEXT
);

-- Why everything is TEXT at the raw layer:
-- Your data has dirty values (blank strings, stray whitespace, malformed
-- dates like "24-07-2023"). If you type these columns as INT/DATE now,
-- the load will silently fail or reject rows on bad data -- which defeats
-- the purpose of a project about DETECTING bad data. Cast to proper types
-- only in `staging`, after your quality rules have already measured the mess.