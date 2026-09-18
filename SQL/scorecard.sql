-- =========================================================
-- Phase 6: Quality Scoring
-- Run AFTER 03_quality_rules.sql has populated governance.violations_log.
-- =========================================================

-- ---------------------------------------------------------
-- 1) Row counts per table -- the denominator for every score.
--    Re-run this each time you re-score (row counts can change).
-- ---------------------------------------------------------
DROP TABLE IF EXISTS governance.table_row_counts;
CREATE TABLE governance.table_row_counts AS
SELECT 'products' AS table_name, COUNT(*) AS row_count FROM raw.products
UNION ALL SELECT 'suppliers', COUNT(*) FROM raw.suppliers
UNION ALL SELECT 'inventory', COUNT(*) FROM raw.inventory
UNION ALL SELECT 'inventory_transactions', COUNT(*) FROM raw.inventory_transactions
UNION ALL SELECT 'purchase_orders', COUNT(*) FROM raw.purchase_orders;

-- ---------------------------------------------------------
-- 2) Score per (table, dimension): 1 - violations/row_count
--    This is a point-in-time view -- always reflects the CURRENT
--    contents of violations_log and table_row_counts.
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.quality_scorecard AS
SELECT
    v.table_name,
    v.dimension,
    COUNT(*)                                  AS violation_count,
    r.row_count,
    ROUND(
        1.0 - (COUNT(*)::NUMERIC / NULLIF(r.row_count, 0)), 4
    )                                          AS quality_score
FROM governance.violations_log v
JOIN governance.table_row_counts r ON v.table_name = r.table_name
GROUP BY v.table_name, v.dimension, r.row_count
ORDER BY v.table_name, v.dimension;

-- ---------------------------------------------------------
-- 3) Domain-level rollup: average score across dimensions per table
--    ("domain" = table here; rename if your framework groups
--    multiple tables into one business domain, e.g. Inventory =
--    inventory + inventory_transactions)
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW governance.quality_scorecard_domain AS
SELECT
    table_name AS domain,
    ROUND(AVG(quality_score), 4) AS overall_score,
    SUM(violation_count) AS total_violations
FROM governance.quality_scorecard
GROUP BY table_name
ORDER BY overall_score ASC;  -- worst domains first, for remediation priority

-- ---------------------------------------------------------
-- 4) Historical snapshot table -- append a row here each time you
--    re-run the pipeline, so Power BI can plot a trend line instead
--    of just a single point-in-time score.
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS governance.quality_scorecard_history (
    measured_at     TIMESTAMP DEFAULT NOW(),
    table_name       TEXT,
    dimension         TEXT,
    violation_count    INTEGER,
    row_count           INTEGER,
    quality_score        NUMERIC
);

INSERT INTO governance.quality_scorecard_history
    (table_name, dimension, violation_count, row_count, quality_score)
SELECT table_name, dimension, violation_count, row_count, quality_score
FROM governance.quality_scorecard;

-- Run this INSERT again after each remediation pass (Phase 5 re-run +
-- Phase 3 re-run) to build up the trend. A simple way to re-score end to
-- end: re-run 01->05 in sequence, or wrap them in a shell/Python driver
-- script later once the manual flow feels solid.

-- Quick checks:
-- SELECT * FROM governance.quality_scorecard_domain;
-- SELECT * FROM governance.quality_scorecard ORDER BY quality_score ASC;