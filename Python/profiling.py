"""
Phase 2: Data profiling (now includes date format validation).
Reads directly from the CSVs and writes governance/*.csv reports.

Run: python python/profiling.py
"""
import re
import pandas as pd

FILES = {
    "products":               "D:/ERP data governance/data/erp_products.csv",
    "suppliers":               "D:/ERP data governance/data/erp_suppliers.csv",
    "inventory":                "D:/ERP data governance/data/erp_inventory.csv",
    "inventory_transactions":   "D:/ERP data governance/data/erp_inventory_transactions.csv",
    "purchase_orders":          "D:/ERP data governance/data/erp_purchase_orders.csv",
}

PREFIX_RE = re.compile(r"^[A-Za-z]+")

# table -> {column: expected strftime format}
# This is the DOMINANT format per column -- anything that fails to parse
# against it is logged as a date format violation (see check_date_formats).
DATE_COLUMNS = {
    "purchase_orders": {
        "order_date": "%d-%m-%Y",
        "expected_delivery_date": "%d-%m-%Y",
    },
    "inventory": {
        "last_updated": "%Y-%m-%d",
    },
    "inventory_transactions": {
        "timestamp": "%Y-%m-%dT%H:%M:%S",
    },
}


def profile_table(name, df):
    """Column-level profile: nulls, distinct count, whitespace-dirty text values."""
    rows = []
    for col in df.columns:
        s = df[col]
        n_null = s.isna().sum()
        n_distinct = s.nunique(dropna=True)

        n_whitespace_dirty = 0
        if s.dtype == object:
            n_whitespace_dirty = s.dropna().apply(
                lambda x: isinstance(x, str) and x != x.strip()
            ).sum()

        rows.append({
            "table": name,
            "column": col,
            "row_count": len(df),
            "null_count": n_null,
            "null_pct": round(100 * n_null / len(df), 2),
            "distinct_count": n_distinct,
            "whitespace_dirty_count": n_whitespace_dirty,
        })
    return rows


def duplicate_checks(dfs):
    dupes = []
    p = dfs["products"]
    dupes.append({
        "check": "products.sku duplicated",
        "violation_count": int(p["sku"].duplicated().sum()),
    })
    dupes.append({
        "check": "products.(product_name, supplier_id) duplicated",
        "violation_count": int(p.duplicated(subset=["product_name", "supplier_id"]).sum()),
    })
    dupes.append({
        "check": "suppliers.supplier_id duplicated",
        "violation_count": int(dfs["suppliers"]["supplier_id"].duplicated().sum()),
    })
    return dupes


def referential_integrity_checks(dfs):
    checks = []
    prod_skus = set(dfs["products"]["sku"])
    supplier_ids = set(dfs["suppliers"]["supplier_id"])

    checks.append({
        "check": "products.supplier_id not in suppliers",
        "violation_count": int(
            (~dfs["products"]["supplier_id"].dropna().isin(supplier_ids)).sum()
        ),
    })
    checks.append({
        "check": "inventory.sku not in products",
        "violation_count": int((~dfs["inventory"]["sku"].isin(prod_skus)).sum()),
    })
    checks.append({
        "check": "inventory_transactions.sku not in products",
        "violation_count": int(
            (~dfs["inventory_transactions"]["sku"].isin(prod_skus)).sum()
        ),
    })
    checks.append({
        "check": "purchase_orders.sku not in products",
        "violation_count": int((~dfs["purchase_orders"]["sku"].isin(prod_skus)).sum()),
    })
    checks.append({
        "check": "purchase_orders.supplier_id not in suppliers",
        "violation_count": int(
            (~dfs["purchase_orders"]["supplier_id"].isin(supplier_ids)).sum()
        ),
    })
    return checks


def sku_prefix_report(dfs):
    prefixes = dfs["products"]["sku"].apply(lambda x: PREFIX_RE.match(x).group())
    return prefixes.value_counts().to_dict()


def check_date_formats(dfs):
    """
    For every column listed in DATE_COLUMNS, try to parse it against its
    expected format. errors="coerce" turns anything that doesn't match into
    NaT instead of crashing -- so a non-null original value that comes back
    NaT is a genuine format violation, and we log the raw offending value.
    Returns a list of violation dicts (one row per bad value).
    """
    violations = []

    for table_name, columns in DATE_COLUMNS.items():
        df = dfs[table_name]
        for col, fmt in columns.items():
            parsed = pd.to_datetime(df[col], format=fmt, errors="coerce")
            bad_mask = df[col].notna() & parsed.isna()
            n_bad = int(bad_mask.sum())

            for raw_value in df.loc[bad_mask, col]:
                violations.append({
                    "table": table_name,
                    "column": col,
                    "expected_format": fmt,
                    "raw_value": raw_value,
                })

            print(f"  {table_name}.{col}: {n_bad} value(s) do not match {fmt}")

    return violations


def main():
    dfs = {name: pd.read_csv(path, dtype=str) for name, path in FILES.items()}

    column_rows = []
    for name, df in dfs.items():
        column_rows.extend(profile_table(name, df))
    column_profile = pd.DataFrame(column_rows)

    dup_report = pd.DataFrame(duplicate_checks(dfs))
    fk_report = pd.DataFrame(referential_integrity_checks(dfs))

    column_profile.to_csv("governance/profiling_column_summary.csv", index=False)
    dup_report.to_csv("governance/profiling_duplicate_checks.csv", index=False)
    fk_report.to_csv("governance/profiling_fk_checks.csv", index=False)

    print("=== Column-level nulls (top offenders) ===")
    print(
        column_profile[column_profile["null_count"] > 0]
        .sort_values("null_count", ascending=False)
        .to_string(index=False)
    )

    print("\n=== Duplicate checks ===")
    print(dup_report.to_string(index=False))

    print("\n=== Referential integrity checks ===")
    print(fk_report.to_string(index=False))

    print("\n=== SKU prefix distribution ===")
    print(sku_prefix_report(dfs))

    print("\n=== Date format checks ===")
    date_violations = check_date_formats(dfs)
    date_violations_df = pd.DataFrame(date_violations)
    date_violations_df.to_csv("governance/profiling_date_format_violations.csv", index=False)
    print(f"  Total date format violations: {len(date_violations_df)}")


if __name__ == "__main__":
    main()