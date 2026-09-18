"""
Phase 6: Quality scoring (Python/CSV version).
Mirrors the same rules as sql/03_quality_rules.sql + sql/05_quality_scorecard.sql
so you can sanity-check the SQL output, or run scoring before your Postgres
pipeline is fully wired up.

Run: python python/05_quality_scoring.py
"""
import pandas as pd

FILES = {
    "products":               "D:/ERP data governance/data/erp_products.csv",
    "suppliers":               "D:/ERP data governance/data/erp_suppliers.csv",
    "inventory":                "D:/ERP data governance/data/erp_inventory.csv",
    "inventory_transactions":   "D:/ERP data governance/data/erp_inventory_transactions.csv",
    "purchase_orders":          "D:/ERP data governance/data/erp_purchase_orders.csv",
}


def collect_violations(dfs):
    """Same rule set as sql/03_quality_rules.sql, one row per violation."""
    v = []
    p, s = dfs["products"], dfs["suppliers"]
    inv, txn, po = dfs["inventory"], dfs["inventory_transactions"], dfs["purchase_orders"]

    # completeness
    for col in ["category", "price", "supplier_id"]:
        for sku in p.loc[p[col].isna(), "sku"]:
            v.append(("products", "completeness", sku))
    for col in ["qty_ordered", "order_date", "delivery_status"]:
        for pid in po.loc[po[col].isna(), "purchase_order_id"]:
            v.append(("purchase_orders", "completeness", pid))

    # uniqueness
    dup_mask = p.duplicated(subset=["product_name", "supplier_id"], keep=False) & \
               p.duplicated(subset=["product_name", "supplier_id"])
    for sku in p.loc[dup_mask, "sku"]:
        v.append(("products", "uniqueness", sku))

    # validity: orphan supplier
    supplier_ids = set(s["supplier_id"])
    orphan_mask = p["supplier_id"].notna() & ~p["supplier_id"].isin(supplier_ids)
    for sku in p.loc[orphan_mask, "sku"]:
        v.append(("products", "validity", sku))

    # consistency: non-canonical category / status / type / sku prefix
    for sku, val in p.loc[p["category"].notna(), ["sku", "category"]].values:
        if val != val.strip().title():
            v.append(("products", "consistency", sku))
    for pid, val in po.loc[po["delivery_status"].notna(), ["purchase_order_id", "delivery_status"]].values:
        if val != val.strip().title():
            v.append(("purchase_orders", "consistency", pid))
    for tid, val in txn.loc[txn["transaction_type"].notna(), ["transaction_id", "transaction_type"]].values:
        if val != val.strip().upper():
            v.append(("inventory_transactions", "consistency", tid))

    # accuracy: date format violations (reuse the same check as profiling.py)
    date_cols = {
        "purchase_orders": {"order_date": "%d-%m-%Y", "expected_delivery_date": "%d-%m-%Y"},
        "inventory": {"last_updated": "%Y-%m-%d"},
    }
    for table_name, cols in date_cols.items():
        df = dfs[table_name]
        id_col = "purchase_order_id" if table_name == "purchase_orders" else "sku"
        for col, fmt in cols.items():
            parsed = pd.to_datetime(df[col], format=fmt, errors="coerce")
            bad_mask = df[col].notna() & parsed.isna()
            for record_id in df.loc[bad_mask, id_col]:
                v.append((table_name, "accuracy", record_id))

    return pd.DataFrame(v, columns=["table_name", "dimension", "record_id"])


def main():
    dfs = {name: pd.read_csv(path, dtype=str) for name, path in FILES.items()}
    row_counts = {name: len(df) for name, df in dfs.items()}

    violations = collect_violations(dfs)
    violations.to_csv("governance/violations_log.csv", index=False)

    scorecard = (
        violations.groupby(["table_name", "dimension"])
        .size()
        .reset_index(name="violation_count")
    )
    scorecard["row_count"] = scorecard["table_name"].map(row_counts)
    scorecard["quality_score"] = (
        1 - scorecard["violation_count"] / scorecard["row_count"]
    ).round(4)

    scorecard.to_csv("governance/quality_scorecard.csv", index=False)

    domain_rollup = (
        scorecard.groupby("table_name")
        .agg(overall_score=("quality_score", "mean"), total_violations=("violation_count", "sum"))
        .reset_index()
        .sort_values("overall_score")
    )
    domain_rollup.to_csv("governance/quality_scorecard_domain.csv", index=False)

    print("=== Scorecard by table x dimension ===")
    print(scorecard.to_string(index=False))
    print("\n=== Domain rollup (worst first) ===")
    print(domain_rollup.to_string(index=False))
    print(f"\nTotal violations across all rules: {len(violations)}")


if __name__ == "__main__":
    main()