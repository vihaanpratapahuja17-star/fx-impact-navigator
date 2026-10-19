"""Exposure analytics derived from the transaction register."""

from __future__ import annotations

import pandas as pd

from .fx_calculations import inr_value, budget_variance


def enrich_transactions(transactions: pd.DataFrame, rates: dict[str, float], stress_pct: float = 5.0, risk_limit_inr: float = 250_000, near_due_days: int = 14, today=None) -> pd.DataFrame:
    frame = transactions.copy()
    if frame.empty:
        for column in ("budget_inr", "reference_inr", "variance_inr", "stress_impact_inr", "days_to_due", "risk_status"):
            frame[column] = pd.Series(dtype=float if column != "risk_status" else str)
        return frame
    today = pd.Timestamp(today or pd.Timestamp.today().date()).date()
    values = []
    for row in frame.to_dict("records"):
        amount = float(row["amount"])
        budget_rate = float(row["budget_rate"])
        kind = str(row["transaction_type"]).lower()
        settled = str(row.get("status", "Open")).lower() == "settled"
        if settled:
            current = float(row["settlement_rate"])
            rate_source = "actual settlement"
        else:
            current = rates.get(str(row["currency"]).upper())
            rate_source = "reference rate" if current else "budget-rate proxy"
        budget = inr_value(amount, budget_rate)
        reference = inr_value(amount, current) if current else None
        variance = budget_variance(amount, current, budget_rate, kind) if current else None
        adverse_move = stress_pct if kind == "payable" else -stress_pct
        stress_rate = (current if current else budget_rate) * (1 + adverse_move / 100)
        stress_impact = abs(budget_variance(amount, stress_rate, budget_rate, kind))
        due = pd.to_datetime(row["due_date"]).date()
        days = (due - today).days
        status = "Settled" if settled else ("Overdue" if days < 0 else "Due soon" if days <= near_due_days else "Review" if stress_impact >= risk_limit_inr else "Within limits")
        values.append({"applied_rate": current, "rate_source": rate_source, "budget_inr": budget, "reference_inr": reference, "variance_inr": variance, "stress_impact_inr": stress_impact, "days_to_due": days, "risk_status": status})
    return pd.concat([frame.reset_index(drop=True), pd.DataFrame(values)], axis=1)


def exposure_by_currency(enriched: pd.DataFrame) -> pd.DataFrame:
    if enriched.empty:
        return pd.DataFrame(columns=["currency", "payables_fc", "receivables_fc", "net_payable_fc", "payables_inr", "receivables_inr", "net_payable_inr"])
    open_rows = enriched[~enriched["status"].astype(str).str.lower().isin(["settled", "cancelled"])]
    rows = []
    for currency, group in open_rows.groupby("currency"):
        pay = group[group["transaction_type"] == "payable"]
        rec = group[group["transaction_type"] == "receivable"]
        pay_inr = pay["reference_inr"].fillna(pay["budget_inr"]).sum()
        rec_inr = rec["reference_inr"].fillna(rec["budget_inr"]).sum()
        rows.append({"currency": currency, "payables_fc": pay["amount"].sum(), "receivables_fc": rec["amount"].sum(), "net_payable_fc": pay["amount"].sum() - rec["amount"].sum(), "payables_inr": pay_inr, "receivables_inr": rec_inr, "net_payable_inr": pay_inr - rec_inr})
    return pd.DataFrame(rows).sort_values("currency").reset_index(drop=True)


def potential_offsets(enriched: pd.DataFrame, bucket_days: int = 30) -> pd.DataFrame:
    """Report same-currency, near-maturity offsets as opportunities only."""
    if enriched.empty:
        return pd.DataFrame(columns=["currency", "maturity_bucket", "payables_fc", "receivables_fc", "potential_offset_fc", "residual_payable_fc"])
    frame = enriched[~enriched["status"].astype(str).str.lower().isin(["settled", "cancelled"])].copy()
    if bucket_days <= 0:
        raise ValueError("bucket_days must be positive")
    frame["maturity_bucket"] = frame["days_to_due"].apply(lambda d: "Overdue" if d < 0 else f"{int(d)//bucket_days * bucket_days}–{int(d)//bucket_days * bucket_days + bucket_days} days")
    pivot = frame.pivot_table(index=["currency", "maturity_bucket"], columns="transaction_type", values="amount", aggfunc="sum", fill_value=0).reset_index()
    if "payable" not in pivot: pivot["payable"] = 0.0
    if "receivable" not in pivot: pivot["receivable"] = 0.0
    pivot = pivot.rename(columns={"payable": "payables_fc", "receivable": "receivables_fc"})
    pivot["potential_offset_fc"] = pivot[["payables_fc", "receivables_fc"]].min(axis=1)
    pivot["residual_payable_fc"] = pivot["payables_fc"] - pivot["potential_offset_fc"]
    return pivot
