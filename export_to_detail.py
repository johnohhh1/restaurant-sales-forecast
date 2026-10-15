#!/usr/bin/env python3
"""
export_to_detail.py — Flatten a hierarchical "Sales and Cust Count" POS export
into a clean UTF-8 CSV that keeps the daypart and order-type split
(total / dinner / lunch x dine-in / to-go, for net sales and customers).

Use export_to_daily.py instead if you only need date,net_sales,customers for
forecasting.

    python export_to_detail.py --in "Sales and Cust Count.csv" --out sales_detail.csv
"""

import argparse
import re

import pandas as pd

COLUMNS = [
    'year', 'quarter', 'month', 'week', 'day_of_week', 'col6',
    'total_net_total',    'dinner_net_total',   'lunch_net_total',
    'total_cust_total',   'dinner_cust_total',  'lunch_cust_total',
    'total_net_dinein',   'total_net_togo',
    'dinner_net_dinein',  'dinner_net_togo',
    'lunch_net_dinein',   'lunch_net_togo',
    'total_cust_dinein',  'total_cust_togo',
    'dinner_cust_dinein', 'dinner_cust_togo',
    'lunch_cust_dinein',  'lunch_cust_togo',
]
KEEP = [
    'year', 'month', 'week', 'day_of_week',
    'total_net_dinein',   'total_net_togo',
    'dinner_net_dinein',  'dinner_net_togo',
    'lunch_net_dinein',   'lunch_net_togo',
    'total_cust_dinein',  'total_cust_togo',
    'dinner_cust_dinein', 'dinner_cust_togo',
    'lunch_cust_dinein',  'lunch_cust_togo',
]
VALID_DAYS = {'Thr', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue', 'Wed'}


def clean_num(val):
    if pd.isna(val):
        return ''
    return re.sub(r'[\$,\s]', '', str(val))


def main():
    ap = argparse.ArgumentParser(description="Flatten a Sales and Cust Count export, keeping daypart detail")
    ap.add_argument("--in", dest="infile", required=True, help="Raw export (UTF-16, tab-delimited)")
    ap.add_argument("--out", default="sales_detail.csv", help="Output CSV path")
    ap.add_argument("--encoding", default="utf-16", help="Input encoding (default utf-16)")
    args = ap.parse_args()

    # Skip the two merged header rows
    df = pd.read_csv(args.infile, sep='\t', encoding=args.encoding, header=None, skiprows=2, dtype=str)
    df.columns = COLUMNS

    # Keep only day-level rows (day_of_week is an actual day, not a rollup)
    df = df[df['day_of_week'].isin(VALID_DAYS)].copy()
    df = df[KEEP]

    for col in df.columns[4:]:  # skip the label columns
        df[col] = df[col].apply(clean_num)

    df.to_csv(args.out, index=False, encoding='utf-8')
    print(f"Done. {len(df)} day-level rows written to {args.out}")
    print(df.head(10).to_string())


if __name__ == "__main__":
    main()
