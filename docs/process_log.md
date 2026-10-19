# Process log

| Step | Approach or decision | Reason and effect |
|---|---|---|
| 1 | Read the Business Analytics marking rubric and the supplied FX build prompt separately. | Kept the app requirements distinct from the academic Theme 1 requirements. The app includes a CSV pathway for a live evaluator dataset. |
| 2 | Set up a modular Streamlit project with separate calculation, validation, persistence, market-data, risk, cash-flow, and reporting modules. | Keeps the financial formulas testable without launching the interface and makes the viva explanation easier to follow. |
| 3 | Defined the FX quote convention as INR per one unit of foreign currency. | Makes the base conversion `foreign amount × rate` and keeps the budget-variance sign convention consistent. |
| 4 | Used simple percentage returns, sample standard deviation, a 252-day annualization convention, and historical quantile VaR/CVaR. | These choices are transparent and reproducible. The Methodology page states the assumptions and minimum observation count. |
| 5 | Added explicit unavailable states, a manual rate override, and validated rate-series CSV upload. | The core calculations remain usable if the market-data provider is unavailable and can accept an evaluator-supplied series without pretending it is live market data. |
| 6 | Used local SQLite for transaction records and CSV import/export for portability. | Supports local persistence while avoiding claims that Streamlit Community Cloud storage is durable or multi-user. |
| 7 | Added a deterministic report instead of requiring an LLM key. | Keeps reporting operational without secrets and constrains narrative to verified calculations and documented limitations. |
| 8 | Added synthetic unit tests for core calculations and validation. | Tests are repeatable and do not depend on a market-data provider. Actual test results are recorded in the README only after execution. |

## Local verification

- `pytest -q`: **34 passed** on 2026-10-19. The suite includes deterministic calculation, validation, provider-failure, transaction, cash-flow, and chronological hedge-proxy checks.
- `python -m compileall -q app.py src ui`: completed successfully.
- Opened the local Streamlit app and reviewed the executive dashboard and scenario workflow. The dashboard loaded illustrative transactions and reference-rate data; the scenario page generated the INR impact table and chart.
- Yahoo Finance returned daily USD/INR, EUR/INR, GBP/INR, and JPY/INR observations during the live-data check. The app displays observation and retrieval times separately, with observation timestamps explicitly marked UTC.

## Deferred work

- Jamovi/Excel replication and matching-output evidence are deferred at the user's request.
- The project source, tests, illustrative CSV, and academic documents were uploaded to a private GitHub repository on 2026-10-19. The local SQLite database, virtual environment, and generated caches were excluded. Deployed to Streamlit Community Cloud from the private repository's `main` branch with `app.py` as the entry point. Streamlit installed dependencies from `requirements.txt`, started the server, and the hosted dashboard loaded successfully at https://fx-impact-navigator-iulmtsjzj4hgzdyxi9xpwc.streamlit.app/.
