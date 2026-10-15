#!/usr/bin/env python3
"""
sales_forecast.py — Daily restaurant sales forecasting with TimesFM 2.5

Zero-shot forecast of net sales using Google Research's TimesFM 2.5 (200M).
Outputs a point forecast plus P10/P50/P90 bands (the bands are the useful part
for labor + prep decisions), and rolls the daily forecast up to 4-week fiscal
periods so it drops straight into a period review.

QUICK START
-----------
    # one-time, in a fresh venv (CPU is fine, model is tiny):
    pip install "timesfm[torch]" pandas numpy matplotlib

    # then:
    python sales_forecast.py --csv sales.csv --horizon 56

INPUT
-----
A CSV with one row per day, at minimum a date column and a net-sales column.
Defaults assume columns named "date" and "net_sales" — override with flags.
Example:
    date,net_sales
    2024-04-01,14823.55
    2024-04-02,12119.10
    ...

Run `python sales_forecast.py --help` for all options.
"""

import argparse
import sys
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# 1. Args
# ----------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="TimesFM 2.5 daily sales forecast")
    p.add_argument("--csv", required=True, help="Path to daily sales CSV")
    p.add_argument("--date-col", default="date", help="Name of the date column")
    p.add_argument("--sales-col", default="net_sales", help="Name of the net-sales column")
    p.add_argument("--horizon", type=int, default=56, help="Days to forecast (56 = two 4-week periods)")
    p.add_argument("--context", type=int, default=1024,
                   help="Max history length fed to the model. 1024 days ~= 2.8 yrs. "
                        "Bump toward 16000 if you have more daily history.")
    p.add_argument("--period-start", default=None,
                   help="First day of a 4-week fiscal period (YYYY-MM-DD) to anchor the 4-week rollup. "
                        "Defaults to the first forecast day.")
    p.add_argument("--title", default="Daily Net Sales Forecast (TimesFM 2.5)", help="Chart title")
    p.add_argument("--out-prefix", default="sales_forecast",
                   help="Prefix for output files")
    p.add_argument("--no-plot", action="store_true", help="Skip the PNG chart")
    return p.parse_args()


# ----------------------------------------------------------------------------
# 2. Load + clean
#    Restaurants close some days (e.g. Christmas) and POS exports skip them.
#    TimesFM expects EVENLY SPACED points, so we reindex to a full daily
#    calendar and fill gaps. A true closed day is a real 0 for ops, but a 0
#    teaches the model a phantom weekly dip — so we interpolate small gaps and
#    let you decide on known closures.
# ----------------------------------------------------------------------------
def load_series(path, date_col, sales_col):
    df = pd.read_csv(path)
    if date_col not in df.columns or sales_col not in df.columns:
        sys.exit(f"ERROR: expected columns '{date_col}' and '{sales_col}'. "
                 f"Found: {list(df.columns)}. Use --date-col / --sales-col.")

    df[date_col] = pd.to_datetime(df[date_col])
    df = df[[date_col, sales_col]].dropna(subset=[date_col]).sort_values(date_col)
    df = df.set_index(date_col)

    # Reindex to a gapless daily calendar
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="D")
    n_before = len(df)
    df = df.reindex(full_idx)
    n_filled = int(df[sales_col].isna().sum())

    # Linear-interpolate interior gaps (missing POS rows), then fill any edges
    df[sales_col] = df[sales_col].interpolate(method="linear").ffill().bfill()

    print(f"Loaded {n_before} rows | calendar span {full_idx[0].date()} -> {full_idx[-1].date()} "
          f"({len(full_idx)} days) | filled {n_filled} missing days")
    return df[sales_col]


# ----------------------------------------------------------------------------
# 3. Forecast with TimesFM 2.5
#    NOTE: the 2.5 API differs from 1.x/2.0. There is NO `freq` indicator
#    anymore. We turn on the quantile head for prediction bands and constrain
#    outputs to be positive (sales can't go negative).
# ----------------------------------------------------------------------------
def forecast(series: pd.Series, horizon: int, context: int):
    import torch
    import timesfm

    torch.set_float32_matmul_precision("high")

    print("Loading google/timesfm-2.5-200m-pytorch ...")
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")

    model.compile(
        timesfm.ForecastConfig(
            max_context=context,
            max_horizon=horizon,
            normalize_inputs=True,
            use_continuous_quantile_head=True,  # gives us P10..P90
            force_flip_invariance=True,
            infer_is_positive=True,             # sales >= 0
            fix_quantile_crossing=True,
        )
    )

    # Use the most recent `context` days as the model input
    hist = series.values[-context:].astype(np.float32)

    point, quantile = model.forecast(horizon=horizon, inputs=[hist])
    # point   -> (1, horizon)
    # quantile-> (1, horizon, 10): [:, :, 0]=mean, [:, :, 1..9]=P10,P20,...,P90
    point = point[0]
    q = quantile[0]

    last_day = series.index[-1]
    fut_idx = pd.date_range(last_day + pd.Timedelta(days=1), periods=horizon, freq="D")

    out = pd.DataFrame({
        "date": fut_idx,
        "forecast": point,
        "p10": q[:, 1],   # slow-day floor — don't over-staff below this
        "p50": q[:, 5],   # median
        "p90": q[:, 9],   # busy-day ceiling — staff/prep to here
    }).set_index("date")
    out["dow"] = out.index.day_name()
    return out


# ----------------------------------------------------------------------------
# 4. Roll daily -> 4-week (28-day) fiscal periods
# ----------------------------------------------------------------------------
def period_rollup(daily: pd.DataFrame, period_start):
    anchor = daily.index[0] if period_start is None else pd.to_datetime(period_start)

    daily = daily.copy()
    day_offset = (daily.index - anchor).days
    daily["period"] = (day_offset // 28).astype(int) + 1  # P1, P2, ... within window

    rows = []
    for pnum, g in daily.groupby("period"):
        rows.append({
            "period": f"P{pnum}",
            "start": g.index.min().date(),
            "end": g.index.max().date(),
            "days": len(g),
            "forecast_total": round(g["forecast"].sum(), 2),
            "p10_total": round(g["p10"].sum(), 2),
            "p90_total": round(g["p90"].sum(), 2),
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# 5. Plot
# ----------------------------------------------------------------------------
def plot(history: pd.Series, fc: pd.DataFrame, path: str, title: str, tail_days=120):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(13, 5))
    h = history.iloc[-tail_days:]
    ax.plot(h.index, h.values, color="#1f2937", lw=1, label="Actual")
    ax.plot(fc.index, fc["forecast"], color="#b91c1c", lw=1.6, label="Forecast")
    ax.fill_between(fc.index, fc["p10"], fc["p90"], color="#b91c1c", alpha=0.15,
                    label="P10-P90 band")
    ax.set_title(title)
    ax.set_ylabel("Net sales ($)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    print(f"Wrote chart -> {path}")


# ----------------------------------------------------------------------------
def main():
    args = parse_args()
    series = load_series(args.csv, args.date_col, args.sales_col)
    fc = forecast(series, args.horizon, args.context)

    daily_path = f"{args.out_prefix}_daily.csv"
    fc.to_csv(daily_path)
    print(f"Wrote daily forecast -> {daily_path}")

    periods = period_rollup(fc, args.period_start)
    period_path = f"{args.out_prefix}_periods.csv"
    periods.to_csv(period_path, index=False)
    print(f"Wrote period rollup -> {period_path}")
    print("\nPeriod totals:")
    print(periods.to_string(index=False))

    if not args.no_plot:
        plot(series, fc, f"{args.out_prefix}.png", args.title)


if __name__ == "__main__":
    main()
