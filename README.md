# FX Impact Navigator

Interactive foreign-exchange exposure, cash-flow, and business-impact analysis for an academic Business Analytics project.

## Business problem

Importers and exporters can have foreign-currency invoices due before they know the final INR settlement value. FX Impact Navigator brings the transaction register and exchange-rate assumptions together so a finance team can see gross payables and receivables, compare them with budget rates, and examine what selected shocks or hypothetical hedge coverage could mean for cash flow.

This is a decision-support prototype. It does not predict exchange rates, provide an executable forward quote, guarantee outcomes, or replace professional financial advice.

## Features

- Executive dashboard with filtered exposure, upcoming payments, and risk items.
- Daily FX history and charting using Yahoo Finance via `yfinance` where pairs are available.
- Manual rate override and validated CSV upload for evaluator-supplied or user-supplied rate histories.
- Transaction register with create, edit, delete, search, CSV import, SQLite local persistence, and export.
- Payable and receivable budget variance with consistent adverse-positive sign convention.
- Scenario comparison, profit assumptions, and amount/rate sensitivity heatmap.
- Hypothetical hedge coverage comparison and a clearly labeled prior-close proxy simulation.
- Historical returns, rolling volatility, annualized volatility, historical VaR/CVaR, currency stress tests, and configurable alerts.
- Dated cash-flow forecast, potential natural-offset view, and CSV exports.
- Deterministic management report and methodology documentation.
- Synthetic unit tests independent of the external data provider.

## Technology and structure

Python 3.11+, Streamlit, pandas, NumPy, yfinance, Plotly, and pytest.

```text
app.py
ui/views.py
src/fx_calculations.py
src/market_data.py
src/exposure_manager.py
src/scenario_engine.py
src/hedging.py
src/risk_metrics.py
src/cash_flow.py
src/persistence.py
src/reporting.py
src/validation.py
tests/
data/sample_transactions.csv
docs/
```

## Run locally

From this project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit. The sample transaction file contains illustrative records only. The app stores transactions in `data/fx_navigator.sqlite3`, which is ignored by Git. Set `FXN_DB_PATH` to use a different local database path.

## Run tests

```bash
pytest
```

The tests use deterministic synthetic values and do not require Yahoo Finance. The current local verification run is recorded in `docs/process_log.md`.

## Market data and limitations

The application requests daily close observations from Yahoo Finance through `yfinance`. Tickers and actual provider availability can vary. The UI displays observation and retrieval information when returned and shows a warning when history is unavailable. The common mapping is `INR=X` for USD/INR; other mappings are attempted and should be checked against returned observations before interpreting them.

All business calculations use INR per one foreign-currency unit. A reference observation is not an executable bank price. Uploaded or manual inputs are clearly identified. Missing history is not interpolated for return or volatility analysis. A dashboard total can use an invoice budget rate as a proxy when no current reference rate is available; the UI labels that limitation.

## Calculation definitions

- INR value = foreign-currency amount × INR per foreign-currency unit.
- Payable variance = scenario INR cost − budgeted INR cost.
- Receivable adverse variance = budgeted INR receipt − scenario INR receipt.
- Simple daily return = `S(t) / S(t−1) − 1`.
- Daily volatility is sample standard deviation (`ddof=1`); annualized volatility uses `sqrt(252)`.
- Historical VaR is the empirical quantile of one-day losses (`−return × exposure`). CVaR averages losses at or beyond that quantile. At least 20 observations are required. VaR is not a maximum possible loss.
- Hypothetical hedge settlement cost = `A × [h × F + (1 − h) × S] + costs`; only the covered share is assumed locked at user-entered `F`.
- Historical hedge proxy uses the preceding daily close as an assumed forward reference. It is not a real-forward backtest.

## Academic materials

See `docs/academic_report.md`, `docs/process_log.md`, and `docs/ai_use_declaration.md`. The transaction and market CSV import paths can be used with a dataset supplied during assessment. The required second analysis platform and its matching-output evidence are deferred for a later step.

## Security and deployment

Do not enter confidential company, customer, counterparty, or personal financial data into a public demonstration deployment. No API keys are required for the current feature set. The database is local and is not a durable shared store on Streamlit Community Cloud. Use CSV export to preserve academic data.Repository: [fx-impact-navigator](https://github.com/vihaanpratapahuja17-star/fx-impact-navigator) (public).

The local SQLite file, virtual environment, secret files, and generated caches are excluded from the repository. The illustrative sample CSV contains no real customer data. The app is deployed from the public GitHub repository's `main` branch with `app.py` as its entry point. Both the dashboard and source repository are publicly viewable.

Hosted application URL: https://fx-impact-navigator-iulmtsjzj4hgzdyxi9xpwc.streamlit.app/.


Streamlit Community Cloud can put an app to sleep after 12 hours without traffic. A visitor can wake it by opening the app, but the free hosting tier does not guarantee uninterrupted 24/7 availability. Public apps may also be indexed by search engines. Do not put confidential data in the dashboard.

## Future updates

1. Add new pure calculations to `src/` and cover them with deterministic tests.
2. Keep raw source observations separate from derived analysis columns.
3. Check ticker coverage and timestamps when updating market-data mappings.
4. Add new controls to Settings and persist non-secret preferences in SQLite.
5. Run the test suite and local app smoke check before publishing updates.
6. Never include the local database, secret files, or private transaction exports in a Git commit.

## License

MIT. See `LICENSE`.
