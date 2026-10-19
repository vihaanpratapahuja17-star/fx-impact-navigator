"""Foreign-currency cash-flow forecasts and natural-offset summaries."""

from __future__ import annotations

import pandas as pd


def forecast(transactions: pd.DataFrame, rates: dict[str, float], start_date, end_date, currencies=None, transaction_types=None, stress_pct: float = 5.0) -> pd.DataFrame:
    if start_date > end_date:
        raise ValueError("start_date cannot be after end_date")
    if transactions.empty:
        return pd.DataFrame(columns=["due_date", "currency", "transaction_type", "transactions", "amount_fc", "estimated_inr", "budget_inr", "adverse_inr"])
    frame = transactions.copy()
    frame["due_date"] = pd.to_datetime(frame["due_date"]).dt.date
    frame = frame[(frame["due_date"] >= start_date) & (frame["due_date"] <= end_date)]
    frame = frame[~frame["status"].astype(str).str.lower().isin(["settled", "cancelled"])]
    if currencies is not None: frame = frame[frame["currency"].isin(currencies)]
    if transaction_types is not None: frame = frame[frame["transaction_type"].isin(transaction_types)]
    rows = []
    for row in frame.to_dict("records"):
        rate = rates.get(row["currency"])
        if not rate:
            continue
        amount, budget = float(row["amount"]), float(row["budget_rate"])
        adverse_rate = rate * (1 + (stress_pct if row["transaction_type"] == "payable" else -stress_pct) / 100)
        rows.append({"due_date": row["due_date"], "currency": row["currency"], "transaction_type": row["transaction_type"], "transactions": 1, "amount_fc": amount, "estimated_inr": amount * rate * (1 if row["transaction_type"] == "payable" else -1), "budget_inr": amount * budget * (1 if row["transaction_type"] == "payable" else -1), "adverse_inr": amount * adverse_rate * (1 if row["transaction_type"] == "payable" else -1)})
    if not rows:
        return pd.DataFrame(columns=["due_date", "currency", "transaction_type", "transactions", "amount_fc", "estimated_inr", "budget_inr", "adverse_inr"])
    return pd.DataFrame(rows).groupby(["due_date", "currency", "transaction_type"], as_index=False).agg(transactions=("transactions", "sum"), amount_fc=("amount_fc", "sum"), estimated_inr=("estimated_inr", "sum"), budget_inr=("budget_inr", "sum"), adverse_inr=("adverse_inr", "sum")).sort_values("due_date")
