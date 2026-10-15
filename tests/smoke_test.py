"""Smoke test (no model download needed): synthetic export -> export_to_daily.py -> sales_forecast.py with a stubbed TimesFM."""
import csv, os, runpy, subprocess, sys, tempfile, types
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
raw = os.path.join(tmp, "raw.csv")
dows = ["Thr", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]
with open(raw, "w", encoding="utf-16", newline="") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["Year", "Qtr", "Month", "Week", "DOW"] + [f"c{i}" for i in range(5, 20)])
    for wk in range(1, 21):
        w.writerow(["FY26", "Q1", "M1", f"w{wk}", "Total"] + [""] * 15)  # rollup row: must be skipped
        for d in dows:
            row = ["FY26", "Q1", "M1", f"w{wk}", d] + [""] * 15
            row[12], row[13], row[18], row[19] = "$8,000", "2,000", "300", "50"
            w.writerow(row)
daily = os.path.join(tmp, "sales.csv")
out = subprocess.run([sys.executable, os.path.join(REPO, "export_to_daily.py"), "--in", raw, "--out", daily],
                     capture_output=True, text=True)
assert out.returncode == 0, out.stderr
rows = list(csv.DictReader(open(daily)))
assert len(rows) == 140 and rows[0]["date"] == "2025-06-26" and float(rows[0]["net_sales"]) == 10000.0, rows[:2]
print("converter ok:", out.stdout.splitlines()[0])


class FakeModel:
    def compile(self, cfg): pass

    def forecast(self, horizon, inputs):
        n = horizon
        point = np.full((1, n), 10000.0)
        q = np.stack([np.full(n, 10000.0 + 500 * (i - 5)) for i in range(10)], axis=-1)[None]
        return point, q


timesfm = types.SimpleNamespace(
    TimesFM_2p5_200M_torch=types.SimpleNamespace(from_pretrained=lambda name: FakeModel()),
    ForecastConfig=lambda **kw: kw)
torch = types.SimpleNamespace(set_float32_matmul_precision=lambda x: None)
sys.modules["timesfm"] = timesfm
sys.modules["torch"] = torch
os.chdir(tmp)
sys.argv = ["sales_forecast.py", "--csv", daily, "--horizon", "56", "--no-plot"]
runpy.run_path(os.path.join(REPO, "sales_forecast.py"), run_name="__main__")
import pandas as pd
p = pd.read_csv("sales_forecast_periods.csv")
assert list(p["period"]) == ["P1", "P2"] and p["forecast_total"].iloc[0] == 280000.0, p
print("forecast pipeline ok (stub model)")
