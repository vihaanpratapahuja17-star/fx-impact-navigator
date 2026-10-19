"""Hypothetical hedge comparison and chronological policy backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .fx_calculations import hedged_settlement_cost


def compare_hedges(amount: float, forward_rate: float, settlement_rates: dict[str, float], budget_rate: float, coverage_levels=(0, 25, 50, 75, 100), transaction_cost: float = 0) -> pd.DataFrame:
    rows = []
    for scenario, spot in settlement_rates.items():
        for coverage in coverage_levels:
            result = hedged_settlement_cost(amount, forward_rate, spot, coverage, transaction_cost)
            rows.append({"scenario": scenario, "coverage_pct": coverage, "settlement_spot": spot, "budget_inr": amount * budget_rate, "variance_from_budget": result["total_cost"] - amount * budget_rate, **result})
    return pd.DataFrame(rows)


def backtest_policy(rates: pd.Series, amount: float, budget_rate: float, coverage_pct: float, transaction_cost: float = 0.0) -> pd.DataFrame:
    """One-step rolling proxy: prior observation sets the forward assumption.

    This is a simplified historical simulation, not a forward-price backtest.
    Each row uses only the previous close as the assumed covered rate.
    """
    series = pd.to_numeric(rates, errors="coerce").dropna().astype(float).sort_index()
    if len(series) < 3:
        return pd.DataFrame(columns=["date", "spot", "assumed_forward", "unhedged_cost", "policy_cost"])
    rows = []
    for i in range(1, len(series)):
        spot, assumed_forward = float(series.iloc[i]), float(series.iloc[i - 1])
        policy = hedged_settlement_cost(amount, assumed_forward, spot, coverage_pct, transaction_cost)
        rows.append({"date": series.index[i], "spot": spot, "assumed_forward": assumed_forward, "unhedged_cost": amount * spot, "policy_cost": policy["total_cost"], "variance_vs_budget": policy["total_cost"] - amount * budget_rate})
    return pd.DataFrame(rows)
