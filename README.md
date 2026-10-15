# Restaurant Sales Forecast

Zero-shot daily sales forecasting for a single restaurant with Google Research's [TimesFM 2.5](https://github.com/google-research/timesfm). It needs no training: feed it your daily net-sales history and get a point forecast plus P10/P50/P90 bands, rolled up into 4-week fiscal periods.

The bands are the useful part. Staff and prep to around P90 on busy days, and don't over-staff below P10 on slow ones.

| Script | What it does |
|---|---|
| `sales_forecast.py` | Forecasts N days ahead and writes daily and period CSVs plus a chart |
| `export_to_daily.py` | Converts a hierarchical "Sales and Cust Count" POS export (UTF-16, tab-delimited, Year > Quarter > Month > Week > Day rows, Dine In and To Go split) into a clean `date,net_sales,customers` CSV |
| `export_to_detail.py` | Flattens the same export but keeps the lunch/dinner and dine-in/to-go columns, for your own analysis |

## Install

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The model is small (200M parameters) and runs fine on CPU. The first run downloads it from Hugging Face.

## Usage

```bash
# If your POS gives you the hierarchical export, flatten it first
python export_to_daily.py --in "Sales and Cust Count.csv" --out sales.csv --fy-start 2025-06-26

# Forecast the next 8 weeks (two 4-week periods)
python sales_forecast.py --csv sales.csv --horizon 56
```

Outputs:

- `sales_forecast_daily.csv`: date, forecast, p10, p50, p90, weekday
- `sales_forecast_periods.csv`: 28-day period totals (forecast, P10, P90)
- `sales_forecast.png`: last 120 days of actuals with the forecast band

Any CSV with a date column and a sales column works. Use `--date-col` and `--sales-col` if your columns are named differently. Other options include `--context` (how much history the model sees), `--period-start` (anchor the 4-week rollup to your fiscal calendar), `--title`, `--out-prefix` and `--no-plot`. Run `--help` for the full list.

Missing days, like a POS gap or a holiday closure, are filled by linear interpolation, because TimesFM needs evenly spaced points. A real zero would teach the model a fake dip.

`--fy-start` must be the actual calendar date of fiscal week 1's Thursday. It only affects date labels, not the forecast.

## Tests

```bash
python tests/smoke_test.py
```

This builds a synthetic export, converts it, and runs the forecast pipeline with a stubbed model, so it doesn't need PyTorch or a model download.

## Privacy

Sales exports and forecasts are business data. `.gitignore` blocks `*.csv` and `*.png`.

## Contributing

PRs are welcome:

- Converters for other POS export formats (Toast, Square, Aloha, ...) that output the same `date,net_sales,customers` CSV
- Holiday, weather and local-event effects
- Backtesting: hold out the last N weeks and report forecast error

## License

MIT. See [LICENSE](LICENSE). TimesFM is licensed separately by Google (Apache-2.0).
