"""
Phase 1 (continued): Load the 5 CSVs into the `raw` schema exactly as-is.
Run from the project root: python python/01_load_raw.py

Requires: pandas, sqlalchemy, psycopg2-binary
    pip install pandas sqlalchemy psycopg2-binary
"""
import pandas as pd
from sqlalchemy import create_engine
from Db_config import CONN_STRING

# filename -> target table in the `raw` schema
FILES = {
    "D:/ERP data governance/data/erp_products.csv":                "products",
    "D:/ERP data governance/data/erp_suppliers.csv":                "suppliers",
    "D:/ERP data governance/data/erp_inventory.csv":                "inventory",
    "D:/ERP data governance/data/erp_inventory_transactions.csv":   "inventory_transactions",
    "D:/ERP data governance/data/erp_purchase_orders.csv":          "purchase_orders",
}

def load_all():
    engine = create_engine(CONN_STRING)

    for filepath, table_name in FILES.items():
        # dtype=str keeps every column as text -- we do NOT want pandas
        # inferring types here. A dirty "current_stock" like "" or "N/A"
        # would otherwise crash the load or get silently coerced.
        df = pd.read_csv(filepath, dtype=str, keep_default_na=True)

        df.to_sql(
            table_name,
            engine,
            schema="raw",
            if_exists="append",   # table already created by 01_schema.sql
            index=False,
        )
        print(f"Loaded {len(df):>5} rows -> raw.{table_name}")

    engine.dispose()


if __name__ == "__main__":
    load_all()