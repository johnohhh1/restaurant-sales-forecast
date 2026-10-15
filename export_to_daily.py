#!/usr/bin/env python3
"""
export_to_daily.py — Convert a hierarchical "Sales and Cust Count" POS export into a
clean daily CSV that sales_forecast.py can read.

The raw export is UTF-16, tab-delimited, and hierarchical: it nests
Year > Quarter > Month > Week > Day as rows, splits every metric into
Dine In + To Go columns (the combined "Total" columns are left blank), and
its date column is a useless constant ("1/1"). This script:

  1. reads the UTF-16 / tab file
  2. keeps only true day-level rows (day-of-week = Thr/Fri/Sat/Sun/Mon/Tue/Wed)
  3. computes Total Net = Total Net Dine In + Total Net To Go
     and Total Customers = Total Cust Dine In + Total Cust To Go
  4. reconstructs the real calendar date from fiscal week # + day-of-week
  5. writes date,net_sales,customers sorted chronologically

USAGE
-----
    python export_to_daily.py --in "Sales and Cust Count.csv" --out sales.csv
    # then:
    python sales_forecast.py --csv sales.csv --horizon 56

FISCAL ANCHOR
-------------
The export's fiscal weeks run Thursday->Wednesday and FY26 week 1 begins
Thu 2025-06-26 (the Thursday after the last Wednesday of June 2025). That is
the default. If your export is a different year, pass --fy-start YYYY-MM-DD
with the real date of "w1 Thr". The anchor only affects the date *labels*, not
the forecast shape, but get it right so output dates line up with your calendar.
"""

import argparse
import csv
import datetime as dt

# Column indices in the raw export (0-based)
COL_YEAR, COL_QTR, COL_MONTH, COL_WEEK, COL_DOW = 0, 1, 2, 3, 4
COL_NET_DINEIN, COL_NET_TOGO = 12, 13         # Total Net: Dine In, To Go
COL_CUST_DINEIN, COL_CUST_TOGO = 18, 19       # Total Customers: Dine In, To Go

DOW_OFFSET = {"Thr": 0, "Fri": 1, "Sat": 2, "Sun": 3, "Mon": 4, "Tue": 5, "Wed": 6}


def money(s: str) -> float:
    """'$10,296' or '7,271' -> 10296.0 / 7271.0 ; blank -> 0.0"""
    s = (s or "").strip().replace("$", "").replace(",", "")
    return float(s) if s else 0.0


def week_num(w: str) -> int:
    """'w1' -> 1, 'w52' -> 52"""
    return int(w.lstrip("wW"))


def main():
    ap = argparse.ArgumentParser(description="Convert a fiscal-week sales export -> clean daily CSV")
    ap.add_argument("--in", dest="infile", required=True, help="Raw export CSV (UTF-16, tab-delimited)")
    ap.add_argument("--out", default="sales.csv", help="Output clean CSV path")
    ap.add_argument("--encoding", default="utf-16", help="Input encoding (default utf-16)")
    ap.add_argument("--fy-start", default="2025-06-26",
                    help="Real calendar date of fiscal week 1, Thursday (YYYY-MM-DD)")
    args = ap.parse_args()

    fy_start = dt.date.fromisoformat(args.fy_start)
    if fy_start.weekday() != 3:  # Monday=0 ... Thursday=3
        print(f"WARNING: --fy-start {fy_start} is a {fy_start.strftime('%A')}, "
              f"not a Thursday. Fiscal weeks in this export start on Thursday.")

    rows = []
    with open(args.infile, encoding=args.encoding) as f:
        for r in csv.reader(f, delimiter="\t"):
            r = [c.strip() for c in r]
            if len(r) <= COL_CUST_TOGO:
                continue
            if r[COL_DOW] not in DOW_OFFSET:   # skip header + Total/rollup rows
                continue
            wk = week_num(r[COL_WEEK])
            date = fy_start + dt.timedelta(days=(wk - 1) * 7 + DOW_OFFSET[r[COL_DOW]])
            net = money(r[COL_NET_DINEIN]) + money(r[COL_NET_TOGO])
            cust = money(r[COL_CUST_DINEIN]) + money(r[COL_CUST_TOGO])
            rows.append((date, round(net, 2), int(cust)))

    rows.sort(key=lambda x: x[0])

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "net_sales", "customers"])
        for date, net, cust in rows:
            w.writerow([date.isoformat(), net, cust])

    total = sum(net for _, net, _ in rows)
    span = f"{rows[0][0]} -> {rows[-1][0]}" if rows else "n/a"
    print(f"Wrote {len(rows)} daily rows to {args.out}")
    print(f"Date span: {span}")
    print(f"Sum of net_sales (sanity vs annual total): ${total:,.2f}")


if __name__ == "__main__":
    main()
