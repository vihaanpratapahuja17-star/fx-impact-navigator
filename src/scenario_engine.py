"""Scenario analysis and sensitivity calculations."""

from __future__ import annotations

import pandas as pd

from .fx_calculations import inr_value, scenario_impact


def compare_scenarios(amount: float, current_rate: float, budget_rate: float, transaction_type: str, movements: dict[str, float]) -> pd.DataFrame:
    rows = []
    for label, movement in movements.items():
        result = scenario_impact(amount, current_rate, budget_rate, movement, transaction_type)
        rows.append({"scenario": label, "movement_pct": movement, **result})
    return pd.DataFrame(rows)


def sensitivity_grid(amounts, rates) -> pd.DataFrame:
    rows = []
    for amount in amounts:
        for rate in rates:
            rows.append({"amount": float(amount), "rate": float(rate), "inr_value": inr_value(float(amount), float(rate))})
    return pd.DataFrame(rows)


def profitability_change(foreign_amount: float, current_rate: float, scenario_rate_value: float, transaction_type: str, sales_revenue_inr: float | None = None, non_fx_cost_inr: float = 0.0) -> dict[str, float | None]:
    current_value = inr_value(foreign_amount, current_rate)
    new_value = inr_value(foreign_amount, scenario_rate_value)
    if transaction_type == "payable":
        current_profit = None if sales_revenue_inr is None else float(sales_revenue_inr) - current_value - non_fx_cost_inr
        new_profit = None if sales_revenue_inr is None else float(sales_revenue_inr) - new_value - non_fx_cost_inr
    else:
        current_profit = None if sales_revenue_inr is None else float(sales_revenue_inr) + current_value - non_fx_cost_inr
        new_profit = None if sales_revenue_inr is None else float(sales_revenue_inr) + new_value - non_fx_cost_inr
    return {"current_inr": current_value, "scenario_inr": new_value, "change_inr": new_value - current_value, "current_profit_inr": current_profit, "scenario_profit_inr": new_profit, "profit_change_inr": None if current_profit is None else new_profit - current_profit}
