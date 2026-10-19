"""Template-based management reporting from verified calculations."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def management_report(enriched: pd.DataFrame, exposure: pd.DataFrame, alerts: pd.DataFrame, data_notes: list[str], business_name: str = "Business") -> str:
    payable = float(exposure["payables_inr"].sum()) if not exposure.empty else 0.0
    receivable = float(exposure["receivables_inr"].sum()) if not exposure.empty else 0.0
    active = enriched[~enriched["status"].astype(str).str.lower().isin(["settled", "cancelled"])] if not enriched.empty else enriched
    largest = active.sort_values("stress_impact_inr", ascending=False).head(5) if not active.empty else active
    out = [f"# FX exposure review — {business_name}", f"Generated: {datetime.now(timezone.utc).isoformat(timespec='minutes')}", "", "## Executive summary", f"Open payables are estimated at INR {payable:,.0f}; open receivables at INR {receivable:,.0f}. Positive net exposure indicates a net payable position, using the available reference rates or budget-rate proxy where market data is unavailable.", "", "## Largest exposures by stress impact"]
    if largest.empty:
        out.append("No open transaction records are available. Add transactions or load the illustrative sample before interpreting exposure.")
    else:
        for row in largest.to_dict("records"):
            out.append(f"- {row['transaction_id']} ({row['currency']} {row['transaction_type']}, due {row['due_date']}): estimated adverse impact INR {float(row['stress_impact_inr']):,.0f}; status {row['risk_status']}.")
    out.extend(["", "## Risk alerts"])
    if alerts.empty:
        out.append("No configured thresholds were breached by the available data.")
    else:
        for row in alerts.head(10).to_dict("records"):
            out.append(f"- {row['alert']} — {row['transaction']}: {row['observed']} (threshold {row['threshold']}).")
    out.extend(["", "## Upcoming payment requirements", "Use the cash-flow forecast page to select a period and inspect estimated payments, receipts, and adverse-rate cash requirements.", "", "## Historical volatility and VaR", "Historical volatility and historical VaR/CVaR are shown in Risk Analytics only when there are sufficient retrieved observations. VaR is a quantile estimate, not a maximum possible loss.", "", "## Hedging comparison", "The Hedging Strategy Lab uses a user-entered assumed forward rate. It models the covered portion as locked at that rate and the remainder at each scenario spot. These results are hypothetical and omit contract-specific terms unless entered by the user.", "", "## Data quality, assumptions and limitations"])
    out.extend([f"- {note}" for note in data_notes] or ["- No additional data-quality warnings were supplied."])
    out.extend(["- Market observations are historical/reference data, not an executable bank quote.", "- Cash-flow values depend on the transaction register and selected exchange rates; they are not guaranteed future cash flows.", "- This educational prototype does not provide personalized financial advice.", "", "## Questions for the finance team", "- Which transactions have confirmed settlement dates and counterparties?", "- Are there suitable natural offsets after considering timing and operational constraints?", "- Has a bank supplied an executable forward quote and all associated costs?"])
    return "\n".join(out)
