"""
ETL pipeline for legacy shipment CSVs.

Run:
    python pipeline/etl.py --input data/raw_shipments.csv --db data/shipments.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

# --- Config: alias map for messy location names -> canonical name ---
CITY_ALIASES = {
    "mumbai": "Mumbai", "bom": "Mumbai", "bombay": "Mumbai",
    "delhi": "Delhi", "new delhi": "Delhi",
    "bangalore": "Bangalore", "blr": "Bangalore",
    "chennai": "Chennai",
    "kolkata": "Kolkata", "calcutta": "Kolkata",
    "hyderabad": "Hyderabad", "hyd": "Hyderabad",
    "pune": "Pune",
}

# Candidate date formats we expect to see in legacy exports
DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]


def normalize_city(raw_value: str) -> str:
    if pd.isna(raw_value):
        return None
    key = str(raw_value).strip().lower()
    return CITY_ALIASES.get(key, str(raw_value).strip().title())


def parse_messy_date(raw_value: str):
    if pd.isna(raw_value) or str(raw_value).strip() == "":
        return None
    value = str(raw_value).strip()
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(value, format=fmt).date().isoformat()
        except ValueError:
            continue
    
    try:
        return pd.to_datetime(value, errors="raise").date().isoformat()
    except Exception:
        print(f"[warn] could not parse date value: {raw_value!r}", file=sys.stderr)
        return None


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Standardize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Standardize locations
    df["origin"] = df["origin"].apply(normalize_city)
    df["destination"] = df["destination"].apply(normalize_city)

    # Parse all date-like columns
    for col in ["ship_date", "delivery_date", "expected_delivery_date"]:
        df[col] = df[col].apply(parse_messy_date)

    # Rebuild route from cleaned cities (source data's "route" abbreviation can be stale)
    df["route"] = df["origin"].str[:3].str.upper() + "-" + df["destination"].str[:3].str.upper()

    # Delay calculation: only computable when both delivery + expected dates exist
    def compute_delay(row):
        if row["delivery_date"] and row["expected_delivery_date"]:
            delivered = pd.to_datetime(row["delivery_date"])
            expected = pd.to_datetime(row["expected_delivery_date"])
            return (delivered - expected).days
        return None

    df["delay_days"] = df.apply(compute_delay, axis=1)
    df["is_delayed"] = df["delay_days"].apply(lambda d: bool(d and d > 0))

    # Drop exact duplicate shipment_ids, keep first
    df = df.drop_duplicates(subset=["shipment_id"], keep="first")

    return df


def load_to_sqlite(df: pd.DataFrame, db_path: str, table_name: str = "shipments"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_route ON {table_name}(route)")
        conn.commit()
    finally:
        conn.close()


def run_pipeline(input_csv: str, db_path: str):
    raw_df = pd.read_csv(input_csv)
    print(f"[info] loaded {len(raw_df)} raw rows from {input_csv}")

    clean_df = clean_dataframe(raw_df)
    print(f"[info] cleaned to {len(clean_df)} rows")

    load_to_sqlite(clean_df, db_path)
    print(f"[info] loaded into {db_path} (table: shipments)")

    return clean_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean messy shipment CSVs and load into SQLite")
    parser.add_argument("--input", default="data/raw_shipments.csv", help="Path to raw CSV")
    parser.add_argument("--db", default="data/shipments.db", help="Path to output SQLite DB")
    args = parser.parse_args()

    run_pipeline(args.input, args.db)
