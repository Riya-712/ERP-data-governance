# Data Quality Report — ERP Master Data Governance Initiative

**Prepared for:** ERP Master Data Governance & Quality Analytics Project
**Scope:** Products, Suppliers, Inventory, Inventory Transactions, Purchase Orders
**Database:** PostgreSQL (`analytics`) | **Tooling:** SQL, Python, Power BI
**Report date:** [insert date of your run]

---

## 1. Executive Summary

A 5-dimension data quality assessment was run across five core ERP tables (11,230 total
records). The assessment identified **768 data quality violations**, concentrated
overwhelmingly in **formatting/consistency issues (68.2%)** rather than missing or
duplicate data. Products was the lowest-scoring domain (quality score **0.76**), driven by
inconsistent SKU key formats, non-canonical category values, and a small number of
orphaned supplier references. A standardization pass resolved the majority of these
issues programmatically; remaining gaps are documented in Section 5 as remediation
candidates requiring manual review.

---

## 2. Scope & Data Inventory

| Table | Row Count | Key Fields Assessed |
|---|---|---|
| `products` | 200 | sku, product_name, category, price, supplier_id |
| `suppliers` | 30 | supplier_id, name, lead_time_days, reliability_score |
| `inventory` | 1,000 | sku, warehouse_id, current_stock, safety_stock, last_updated |
| `inventory_transactions` | 8,000 | transaction_id, sku, transaction_type, quantity_change, timestamp |
| `purchase_orders` | 3,000 | purchase_order_id, supplier_id, sku, qty_ordered, order_date, expected_delivery_date, delivery_status |

---

## 3. Methodology

Data quality was assessed against 5 industry-standard dimensions, each implemented as a
set of SQL rule views in the `governance` schema (see `sql/03_quality_rules.sql` and
`sql/03b_fix_date_parsing.sql`):

| Dimension | Definition | Example rule applied |
|---|---|---|
| **Completeness** | Required fields are populated | `category`, `price`, `supplier_id` not null in `products` |
| **Uniqueness** | No unintended duplicate records | No duplicate `(product_name, supplier_id)` pairs |
| **Validity** | Values conform to allowed types/ranges/references | `supplier_id` must exist in `suppliers`; `price` > 0 |
| **Consistency** | Same fact represented the same way everywhere | Canonical casing for `category`/`delivery_status`/`transaction_type`; single SKU prefix standard; single date format per column |
| **Accuracy** | Values are logically/factually correct | `expected_delivery_date` >= `order_date`; transaction sign matches direction |

Every violation is logged as one row in `governance.violations_log` (columns:
`table_name`, `dimension`, `rule_name`, `record_id`, `detail`), which is the single
source of truth for both this report and the Power BI scorecard.

Quality score per (table, dimension) is calculated as:
```
quality_score = 1 - (violation_count / row_count)
```

---

## 4. Findings

### 4.1 Overall violation summary

**Total violations: 768** across 3 of the 5 assessed tables (no violations were found in
`suppliers` or `inventory` under the current rule set).

| Dimension | Violations | % of Total Violations |
|---|---|---|
| Consistency | 524 | 68.23% |
| Completeness | 210 | 27.34% |
| Accuracy | 21 | 2.73% |
| Uniqueness | 10 | 1.30% |
| Validity | 3 | 0.39% |

> **Interpretation note:** these percentages describe the *composition* of the problem
> (what kind of issue is most common), not the *prevalence* across records. Expressed
> against the full 11,230-row dataset, consistency issues affect roughly **4.7%** of
> records — a small but concentrated and highly fixable class of problems.

### 4.2 Score by domain

| Domain | Quality Score | Violations | Interpretation |
|---|---|---|---|
| Products | 0.76 | 194 | Lowest-scoring domain; driven by SKU/category formatting and 3 orphaned supplier references |
| Purchase Orders | 0.96 | 321 | Mostly date-format inconsistencies and a small completeness gap |
| Inventory Transactions | 0.97 | 253 | Mostly non-canonical `transaction_type` casing |

### 4.3 Notable individual findings

- **Orphaned supplier reference:** 3 product records (`PRO00068`, `SKU00179`,
  `PROD00187`) reference `supplier_id = SUP999`, which does not exist in the `suppliers`
  table — indicating a supplier was deleted or deactivated without a corresponding
  update to dependent product records.
- **SKU key fragmentation:** product SKUs were found under 4 different prefix
  conventions (`PRO`: 60, `SKU`: 50, `PROD`: 50, `ITM`: 40) for what is functionally a
  single identifier type — no governing key standard had been enforced at data entry.
- **Mixed date formats:** three different date formats were in active use across the
  dataset (`DD-MM-YYYY` in purchase orders, `YYYY-MM-DD` in inventory, ISO 8601 in
  transactions), and 94 individual date values did not even match their own column's
  dominant format (e.g. `MM/DD/YYYY` values mixed into a `DD-MM-YYYY` column).
- **Duplicate product records:** 5 pairs of records share the same `(product_name,
  supplier_id)` combination, suggesting possible re-entry of the same product under a
  different SKU.

---

## 5. Remediation Summary

The following corrective actions were executed via `python/04_standardize_enrich.py`
and written to the `staging` schema:

| Issue | Records Affected | Action Taken | Outcome |
|---|---|---|---|
| Non-canonical category casing/whitespace | 10 | Trimmed + title-cased | 100% resolved |
| Null category | 2 | Keyword-based inference from `product_name` | 1 recovered; 1 flagged for manual tagging |
| Inconsistent SKU prefix | 150 of 200 | Rewritten to canonical `SKU` prefix | 100% resolved, zero key collisions |
| Null price | 8 | Imputed via category-level median price | 100% resolved |
| Malformed dates (all 3 date columns) | 94 | Multi-format fallback parsing | 100% recovered, 0 unresolved |

**Not auto-remediated (flagged for manual governance review):**
- 3 orphaned supplier references (`SUP999`) — requires confirming with the source
  system whether the supplier should be reinstated or the products reassigned
- 1 product with no inferable category — requires manual tagging
- 5 duplicate `(product_name, supplier_id)` pairs — requires business confirmation
  before merge/delete, since automatic deduplication risks losing a legitimately
  distinct SKU variant

---

## 6. Recommendations

1. **Enforce a single SKU key standard at the point of entry** (or at system
   integration, if SKUs originate from multiple source systems) to prevent future
   prefix fragmentation.
2. **Add a foreign-key constraint or entry-time validation** on `products.supplier_id`
   to prevent future orphaned references.
3. **Standardize on one date format per system boundary** (e.g. ISO 8601 for all
   inter-system exports) to eliminate the mixed-format class of error entirely rather
   than repeatedly recovering from it downstream.
4. **Re-run this assessment on a recurring cadence** (see the accompanying SOP) and
   track score trend over time via `governance.quality_scorecard_history`, rather than
   treating this as a one-time cleanup.

---

## Appendix A — Full Rule Catalog

See `sql/03_quality_rules.sql` and `sql/03b_fix_date_parsing.sql` for the complete,
version-controlled definition of every rule referenced in this report.
