# FX Impact Navigator

## Summary

FX Impact Navigator is an academic decision-support prototype for analyzing foreign-currency invoices and receipts against INR budgets. It combines transaction-level exposure calculations with historical FX observations, scenarios, risk measures, cash-flow estimates, and hypothetical hedge comparisons.

The project focuses on how exchange-rate changes can affect a company's INR cash requirements and expected receipts before settlement. It does not predict future exchange rates or provide executable currency quotes.

## Objective

The project aims to help an importer, exporter, or finance team identify gross payables and receivables by currency, estimate their INR values, prioritize upcoming exposures, and compare the consequences of selected exchange-rate scenarios. It also provides an auditable basis for explaining analytical choices in a live assessment.

## Data and approach

The application separates company-entered transactions from the market-data feed. Transactions can be entered individually or imported as CSV and are stored in a local SQLite database. Market history is requested from Yahoo Finance via `yfinance` using daily closes where available. Users can supply a manual reference rate or upload an evaluator-provided daily series with date and rate/close columns.

All FX pairs used in business calculations are expressed as INR per one unit of foreign currency. Raw rate observations are kept separate from derived returns. Simple returns use `S(t) / S(t-1) - 1`. Daily volatility is the sample standard deviation of returns, and annualized volatility uses 252 trading observations per year. Historical VaR is the empirical quantile of one-day losses for a selected exposure. CVaR is the average loss at or beyond that quantile, with a minimum of 20 return observations.

## Financial calculations

For amount `A` in foreign currency and an INR-per-unit rate `S`, INR value is `A × S`. Payable budget variance is scenario cost minus budgeted cost. Receivable adverse variance is budgeted receipt minus scenario receipt. Positive variance therefore means an adverse outcome for the business for both transaction types.

The stress module applies the user-selected percentage shock to the INR value of each currency exposure. The hedging module estimates settlement cost as `A × [h × F + (1 − h) × S] + costs`, where the assumed covered portion is locked at the user-entered rate `F`. The application does not source forward rates. Its optional historical policy simulation uses the preceding daily close as a forward-rate proxy, so it is illustrative and is not a backtest of executable forward contracts.

## Outputs and interpretation

The dashboard presents gross and net exposure, upcoming payment estimates, configured alerts, and scenario impact. The market monitor plots rate observations, daily returns, and rolling volatility. Other sections support transaction management, what-if analysis, hedge comparison, historical VaR/CVaR, stress tests, cash-flow forecasting, CSV export, and a deterministic management report.

No empirical performance conclusion is stated in this report. Results depend on the transaction inputs, retrieved observations, user-entered rates, and selected assumptions. The sample invoices are explicitly illustrative. The live assessment should use the evaluator's dataset and should document the returned outputs and interpretation separately.

## Limitations

Yahoo Finance reference observations may be delayed or unavailable and may not match a bank's executable rate. A public Streamlit Community Cloud instance does not provide durable shared SQLite storage. The application does not currently integrate an LLM, persistent cloud database, regulatory market data, or historical forward quotations. The deterministic report is based on calculated outputs only.

This is an educational decision-support prototype. It does not guarantee market outcomes or replace professional financial advice.
