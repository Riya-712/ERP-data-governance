"""
Phase 5: Standardize & Enrich.

What this does, and why each step exists:
  1. Category taxonomy   -> trim/case-normalize to a canonical set, and
                             impute the 2 truly-null categories using a
                             keyword rule against product_name.
  2. SKU prefix           -> rewrite every SKU to one canonical prefix
                             (checked for collisions before committing).
  3. Price imputation     -> fill the 8 null prices with the MEDIAN price
                             for that product's (cleaned) category, since a
                             single global average would be misleading
                             across categories that differ 10x in price.
  4. Date standardization -> parse each date column's dominant format,
                             then try a fallback format on anything that
                             failed, and record what got RECOVERED vs what
                             is still unparseable (governance decision:
                             don't silently guess forever).

Every step prints a before/after count -- these are your resume numbers.
Run: python python/04_standardize_enrich.py
"""
import re
import pandas as pd

PREFIX_RE = re.compile(r"^[A-Za-z]+")
CANONICAL_SKU_PREFIX = "SKU"

# Keyword -> category, used only to fill genuinely NULL categories.
# Extend this list if you add more products later.
CATEGORY_KEYWORDS = {
    "software": "Software",
    "app": "Software",
    "circuit": "Components",
    "board": "Components",
    "pcb": "Components",
    "wrench": "Tools",
    "drill": "Tools",
    "multimeter": "Tools",
    "cable": "Accessories",
    "mount": "Accessories",
    "case": "Accessories",
    "steel": "Materials",
    "wood": "Materials",
    "plastic": "Materials",
    "server": "Hardware",
    "drive": "Hardware",
    "processor": "Electronics",
    "phone": "Electronics",
    "monitor": "Electronics",
}


def standardize_categories(products: pd.DataFrame) -> pd.DataFrame:
    before_null = products["category"].isna().sum()
    before_noncanonical = (
        products["category"].dropna().apply(lambda x: x != x.strip().title())
    ).sum()

    # Step A: trim + title-case everything that already has a value
    products["category_clean"] = products["category"].apply(
        lambda x: x.strip().title() if isinstance(x, str) else x
    )

    # Step B: keyword-based imputation for the still-null rows
    def infer_category(name: str) -> str | None:
        name_lower = name.lower()
        for keyword, category in CATEGORY_KEYWORDS.items():
            if keyword in name_lower:
                return category
        return None

    still_null_mask = products["category_clean"].isna()
    inferred = products.loc[still_null_mask, "product_name"].apply(infer_category)
    products.loc[still_null_mask, "category_clean"] = inferred

    after_null = products["category_clean"].isna().sum()
    recovered = before_null - after_null

    print(f"[category] non-canonical formatting fixed: {before_noncanonical} rows")
    print(f"[category] null before: {before_null}, recovered via keyword match: {recovered}, "
          f"still null (needs manual tagging): {after_null}")

    return products


def standardize_sku_prefix(products: pd.DataFrame) -> pd.DataFrame:
    before_counts = products["sku"].apply(lambda x: PREFIX_RE.match(x).group()).value_counts()

    numeric_suffix = products["sku"].apply(lambda x: PREFIX_RE.sub("", x))
    new_sku = CANONICAL_SKU_PREFIX + numeric_suffix

    collisions = new_sku.duplicated().sum()
    if collisions > 0:
        raise ValueError(
            f"Renaming SKU prefixes to '{CANONICAL_SKU_PREFIX}' creates "
            f"{collisions} duplicate key(s) -- resolve manually before proceeding."
        )

    products["sku_clean"] = new_sku
    n_changed = (products["sku"] != products["sku_clean"]).sum()
    print(f"[sku_prefix] {n_changed} of {len(products)} SKUs rewritten to '{CANONICAL_SKU_PREFIX}' prefix")
    print(f"[sku_prefix] old prefix distribution: {before_counts.to_dict()}")

    return products


def impute_price(products: pd.DataFrame) -> pd.DataFrame:
    products["price"] = pd.to_numeric(products["price"], errors="coerce")
    before_null = products["price"].isna().sum()

    category_median = products.groupby("category_clean")["price"].transform("median")
    products["price_clean"] = products["price"].fillna(category_median)

    after_null = products["price_clean"].isna().sum()
    print(f"[price] null before: {before_null}, imputed via category median: "
          f"{before_null - after_null}, still null (no category to borrow from): {after_null}")

    return products


def standardize_dates(df: pd.DataFrame, column: str, primary_fmt: str, fallback_fmts: list[str]) -> pd.DataFrame:
    parsed = pd.to_datetime(df[column], format=primary_fmt, errors="coerce")
    n_total_nonnull = df[column].notna().sum()
    n_primary_ok = parsed.notna().sum()

    still_bad = df[column].notna() & parsed.isna()
    n_recovered = 0
    for fmt in fallback_fmts:
        retry = pd.to_datetime(df.loc[still_bad, column], format=fmt, errors="coerce")
        recovered_mask = retry.notna()
        parsed.loc[still_bad[still_bad].index[recovered_mask.values]] = retry[recovered_mask].values
        n_recovered += recovered_mask.sum()
        still_bad = df[column].notna() & parsed.isna()

    n_unresolved = still_bad.sum()
    out_col = f"{column}_standardized"
    df[out_col] = parsed

    print(f"[dates] {column}: {n_primary_ok}/{n_total_nonnull} matched primary format, "
          f"{n_recovered} recovered via fallback formats, {n_unresolved} unresolved")

    return df


def main():
    products = pd.read_csv("D:/ERP data governance/data/erp_products.csv", dtype=str)
    po = pd.read_csv("D:/ERP data governance/data/erp_purchase_orders.csv", dtype=str)
    inventory = pd.read_csv("D:/ERP data governance/data/erp_inventory.csv", dtype=str)

    print("--- Products: category taxonomy ---")
    products = standardize_categories(products)

    print("\n--- Products: SKU prefix ---")
    products = standardize_sku_prefix(products)

    print("\n--- Products: price imputation ---")
    products = impute_price(products)

    print("\n--- Purchase orders: date standardization ---")
    po = standardize_dates(po, "order_date", "%d-%m-%Y", ["%m/%d/%Y", "%Y-%m-%d"])
    po = standardize_dates(po, "expected_delivery_date", "%d-%m-%Y", ["%m/%d/%Y", "%Y-%m-%d"])

    print("\n--- Inventory: date standardization ---")
    inventory = standardize_dates(inventory, "last_updated", "%Y-%m-%d", ["%d-%m-%Y", "%m/%d/%Y"])

    # Write cleaned outputs to the staging layer (CSV here; swap to
    # df.to_sql(table, engine, schema="staging", if_exists="replace")
    # once you're pointed at Postgres).
    products.to_csv("governance/staging_products.csv", index=False)
    po.to_csv("governance/staging_purchase_orders.csv", index=False)

    products_final = products[["sku_clean", "product_name", "category_clean", "price_clean", "supplier_id"]]
    products_final.columns = ["sku", "product_name", "category", "price", "supplier_id"]
    products_final.to_csv("governance/staging_products_final.csv", index=False)
    
    inventory.to_csv("governance/staging_inventory.csv", index=False)
    print("\nStaging files written to governance/staging_*.csv")


if __name__ == "__main__":
    main()