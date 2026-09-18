-- =========================================================
-- Phase 3: Data Quality Rule Catalog
-- One view per rule, tagged by dimension, feeding a unified
-- governance.violations_log for the scorecard.
-- Run after 01_schema.sql and after raw data is loaded.
-- =========================================================

-- ---------------------------------------------------------
-- COMPLETENESS
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.v_completeness_products AS
SELECT sku AS record_id, 'products' AS table_name,
       'completeness' AS dimension, 'missing_required_field' AS rule_name,
       CASE WHEN category IS NULL THEN 'category'
            WHEN price IS NULL THEN 'price'
            WHEN supplier_id IS NULL THEN 'supplier_id' END AS detail
FROM raw.products
WHERE category IS NULL OR price IS NULL OR supplier_id IS NULL;

CREATE OR REPLACE VIEW governance.v_completeness_purchase_orders AS
SELECT purchase_order_id AS record_id, 'purchase_orders' AS table_name,
       'completeness' AS dimension, 'missing_required_field' AS rule_name,
       CASE WHEN qty_ordered IS NULL THEN 'qty_ordered'
            WHEN order_date IS NULL THEN 'order_date'
            WHEN delivery_status IS NULL THEN 'delivery_status' END AS detail
FROM raw.purchase_orders
WHERE qty_ordered IS NULL OR order_date IS NULL OR delivery_status IS NULL;

-- ---------------------------------------------------------
-- UNIQUENESS
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.v_uniqueness_products AS
SELECT sku AS record_id, 'products' AS table_name,
       'uniqueness' AS dimension, 'duplicate_product_supplier' AS rule_name,
       'duplicate (product_name, supplier_id) pair' AS detail
FROM (
    SELECT sku, product_name, supplier_id,
           COUNT(*) OVER (PARTITION BY product_name, supplier_id) AS cnt
    FROM raw.products
) t
WHERE cnt > 1;

-- ---------------------------------------------------------
-- VALIDITY (referential integrity)
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.v_validity_orphan_supplier AS
SELECT p.sku AS record_id, 'products' AS table_name,
       'validity' AS dimension, 'orphan_supplier_id' AS rule_name,
       'supplier_id ' || p.supplier_id || ' not found in suppliers' AS detail
FROM raw.products p
LEFT JOIN raw.suppliers s ON TRIM(p.supplier_id) = TRIM(s.supplier_id)
WHERE p.supplier_id IS NOT NULL AND s.supplier_id IS NULL;

CREATE OR REPLACE VIEW governance.v_validity_price_range AS
SELECT sku AS record_id, 'products' AS table_name,
       'validity' AS dimension, 'non_positive_price' AS rule_name,
       'price = ' || price AS detail
FROM raw.products
WHERE price IS NOT NULL AND price::NUMERIC <= 0;

-- ---------------------------------------------------------
-- CONSISTENCY (canonical value / formatting checks)
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.v_consistency_category AS
SELECT sku AS record_id, 'products' AS table_name,
       'consistency' AS dimension, 'non_canonical_category' AS rule_name,
       'category = "' || category || '"' AS detail
FROM raw.products
WHERE category IS NOT NULL
  AND category <> INITCAP(TRIM(category));

CREATE OR REPLACE VIEW governance.v_consistency_delivery_status AS
SELECT purchase_order_id AS record_id, 'purchase_orders' AS table_name,
       'consistency' AS dimension, 'non_canonical_delivery_status' AS rule_name,
       'delivery_status = "' || delivery_status || '"' AS detail
FROM raw.purchase_orders
WHERE delivery_status IS NOT NULL
  AND delivery_status <> INITCAP(TRIM(delivery_status));

CREATE OR REPLACE VIEW governance.v_consistency_transaction_type AS
SELECT transaction_id AS record_id, 'inventory_transactions' AS table_name,
       'consistency' AS dimension, 'non_canonical_transaction_type' AS rule_name,
       'transaction_type = "' || transaction_type || '"' AS detail
FROM raw.inventory_transactions
WHERE transaction_type IS NOT NULL
  AND transaction_type <> UPPER(TRIM(transaction_type));

CREATE OR REPLACE VIEW governance.v_consistency_sku_prefix AS
SELECT sku AS record_id, 'products' AS table_name,
       'consistency' AS dimension, 'non_standard_sku_prefix' AS rule_name,
       'prefix = ' || SUBSTRING(sku FROM '^[A-Za-z]+') AS detail
FROM raw.products
WHERE SUBSTRING(sku FROM '^[A-Za-z]+') <> 'SKU';  -- pick ONE standard prefix

-- ---------------------------------------------------------
-- ACCURACY
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.v_accuracy_po_dates AS
SELECT purchase_order_id AS record_id, 'purchase_orders' AS table_name,
       'accuracy' AS dimension, 'delivery_before_order' AS rule_name,
       'expected_delivery_date before order_date' AS detail
FROM raw.purchase_orders
WHERE order_date IS NOT NULL AND expected_delivery_date IS NOT NULL
  AND TO_DATE(expected_delivery_date, 'DD-MM-YYYY') < TO_DATE(order_date, 'DD-MM-YYYY');

CREATE OR REPLACE VIEW governance.v_accuracy_transaction_sign AS
SELECT transaction_id AS record_id, 'inventory_transactions' AS table_name,
       'accuracy' AS dimension, 'sign_mismatch' AS rule_name,
       transaction_type || ' with quantity_change = ' || quantity_change AS detail
FROM raw.inventory_transactions
WHERE (UPPER(TRIM(transaction_type)) = 'OUTBOUND' AND quantity_change::NUMERIC > 0)
   OR (UPPER(TRIM(transaction_type)) = 'INBOUND'  AND quantity_change::NUMERIC < 0);

-- ---------------------------------------------------------
-- ACCURACY
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION governance.parse_flexible_date(raw_val TEXT)
RETURNS DATE AS $$
DECLARE
    fmts TEXT[] := ARRAY['DD-MM-YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD'];
    fmt  TEXT;
    result DATE;
BEGIN
    IF raw_val IS NULL THEN
        RETURN NULL;
    END IF;
 
    FOREACH fmt IN ARRAY fmts LOOP
        BEGIN
            result := TO_DATE(raw_val, fmt);
            RETURN result;
        EXCEPTION WHEN OTHERS THEN
            -- that format didn't fit this value, try the next one
            CONTINUE;
        END;
    END LOOP;
 
    RETURN NULL;  -- none of the formats worked -- genuinely unparseable
END;
$$ LANGUAGE plpgsql IMMUTABLE;
 
-- ---------------------------------------------------------
-- Fixed version of the accuracy rule: uses the safe parser instead
-- of raw TO_DATE, so a mixed-format value no longer crashes the view.
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.v_accuracy_po_dates AS
SELECT purchase_order_id AS record_id, 'purchase_orders' AS table_name,
       'accuracy' AS dimension, 'delivery_before_order' AS rule_name,
       'expected_delivery_date before order_date' AS detail
FROM raw.purchase_orders
WHERE order_date IS NOT NULL AND expected_delivery_date IS NOT NULL
  AND governance.parse_flexible_date(expected_delivery_date)
      < governance.parse_flexible_date(order_date);



CREATE OR REPLACE VIEW governance.v_consistency_date_format AS
SELECT purchase_order_id AS record_id, 'purchase_orders' AS table_name,
       'consistency' AS dimension, 'non_primary_date_format' AS rule_name,
       'order_date = "' || order_date || '" did not match DD-MM-YYYY' AS detail
FROM raw.purchase_orders
WHERE order_date IS NOT NULL
  AND order_date !~ '^\d{2}-\d{2}-\d{4}$'              -- doesn't LOOK like DD-MM-YYYY
  AND governance.parse_flexible_date(order_date) IS NOT NULL;  -- but IS parseable via fallback

-- =========================================================
-- Unified violations log -- one row per violation, all rules
-- This is the single table your Power BI scorecard queries.
-- =========================================================
DROP TABLE IF EXISTS governance.violations_log;
CREATE TABLE governance.violations_log AS
SELECT * FROM governance.v_completeness_products
UNION ALL SELECT * FROM governance.v_completeness_purchase_orders
UNION ALL SELECT * FROM governance.v_uniqueness_products
UNION ALL SELECT * FROM governance.v_validity_orphan_supplier
UNION ALL SELECT * FROM governance.v_validity_price_range
UNION ALL SELECT * FROM governance.v_consistency_category
UNION ALL SELECT * FROM governance.v_consistency_delivery_status
UNION ALL SELECT * FROM governance.v_consistency_transaction_type
UNION ALL SELECT * FROM governance.v_consistency_sku_prefix
UNION ALL SELECT * FROM governance.v_consistency_date_format
UNION ALL SELECT * FROM governance.v_accuracy_po_dates
UNION ALL SELECT * FROM governance.v_accuracy_transaction_sign;
 

-- Quick sanity check: total violations + breakdown by dimension
-- SELECT dimension, COUNT(*) FROM governance.violations_log GROUP BY dimension ORDER BY 2 DESC;