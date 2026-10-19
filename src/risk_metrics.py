"""Historical return, volatility, VaR/CVaR, stress and alert analytics."""

from __future__ import annotations

import numpy as np
import pandas as pd


def return_series(prices: pd.Series) -> pd.Series:
    return pd.to_numeric(prices, errors="coerce").pct_change().dropna().rename("return")


def volatility_summary(prices: pd.Series, annualization_days: int = 252) -> dict[str, float | int | None]:
    returns = return_series(prices)
    if len(returns) < 2:
        return {"observations": int(len(returns)), "daily_volatility": None, "annualized_volatility": None, "rolling_20_latest": None, "rolling_60_latest": None, "rolling_90_latest": None}
    daily = float(returns.std(ddof=1))
    rolling = returns.rolling
    return {"observations": int(len(returns)), "daily_volatility": daily, "annualized_volatility": daily * np.sqrt(annualization_days), "rolling_20_latest": float(rolling(20).std().dropna().iloc[-1]) if len(returns) >= 20 else None, "rolling_60_latest": float(rolling(60).std().dropna().iloc[-1]) if len(returns) >= 60 else None, "rolling_90_latest": float(rolling(90).std().dropna().iloc[-1]) if len(returns) >= 90 else None}


def historical_var_cvar(returns: pd.Series, exposure_inr: float, confidence: float = 0.95) -> dict[str, float | int]:
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 20:
        raise ValueError("At least 20 return observations are required for historical VaR/CVaR")
    if not 0.5 < confidence < 1:
        raise ValueError("confidence must be between 0.5 and 1")
    if exposure_inr < 0:
        raise ValueError("exposure_inr cannot be negative")
    losses = -values * float(exposure_inr)
    var = float(np.quantile(losses, confidence, method="linear"))
    tail = losses[losses >= var]
    return {"confidence": confidence, "observations": int(len(values)), "var_inr": var, "cvar_inr": float(tail.mean()) if len(tail) else var, "tail_observations": int(len(tail))}


def stress_portfolio(exposures: pd.DataFrame, shocks_pct: dict[str, float]) -> pd.DataFrame:
    if exposures.empty:
        return pd.DataFrame(columns=["currency", "net_payable_inr", "shock_pct", "cash_requirement_change_inr"])
    result = exposures.copy()
    result["shock_pct"] = result["currency"].map(shocks_pct).fillna(0.0).astype(float)
    result["cash_requirement_change_inr"] = result["net_payable_inr"] * result["shock_pct"] / 100
    return result


def build_alerts(enriched: pd.DataFrame, movement_pct: dict[str, float], rolling_vol_pct: dict[str, float], thresholds: dict[str, float], timestamp: str) -> pd.DataFrame:
    rows = []
    for currency, value in movement_pct.items():
        threshold = thresholds.get("movement_pct", 5)
        if abs(value) >= threshold:
            severity = abs(value) / threshold if threshold > 0 else 99.0
            rows.append({"rank": 0, "severity": severity, "alert": "Exchange-rate move", "transaction": currency, "observed": f"{value:+.2f}%", "threshold": f"±{threshold:.2f}%", "implication": "Review open cash flows in this currency", "timestamp": timestamp})
    for currency, value in rolling_vol_pct.items():
        threshold = thresholds.get("volatility_pct", 2)
        if value >= threshold:
            severity = value / threshold if threshold > 0 else 99.0
            rows.append({"rank": 0, "severity": severity, "alert": "Rolling volatility", "transaction": currency, "observed": f"{value:.2f}%", "threshold": f"{threshold:.2f}%", "implication": "Uncertainty in INR settlement values is elevated", "timestamp": timestamp})
    if not enriched.empty:
        active = enriched[~enriched["status"].astype(str).str.lower().isin(["settled", "cancelled"])]
        for row in active.to_dict("records"):
            triggers = []
            overrun_limit = thresholds.get("overrun_inr", 250_000)
            due_limit = thresholds.get("near_due_days", 14)
            exposure_limit = thresholds.get("exposure_limit_inr", 1_000_000)
            stress_value = float(row.get("stress_impact_inr", 0))
            budget_value = float(row.get("budget_inr", 0))
            days_to_due = int(row.get("days_to_due", 9999))
            severity_parts = []
            if stress_value >= overrun_limit:
                triggers.append("potential cost overrun")
                severity_parts.append(stress_value / overrun_limit if overrun_limit > 0 else 99.0)
            if days_to_due <= due_limit:
                triggers.append("payment due soon")
                severity_parts.append((due_limit + 1) / max(days_to_due + 1, 1))
            if budget_value >= exposure_limit:
                triggers.append("exposure limit")
                severity_parts.append(budget_value / exposure_limit if exposure_limit > 0 else 99.0)
            if triggers:
                rows.append({"rank": 0, "severity": max(severity_parts), "alert": ", ".join(triggers), "transaction": row["transaction_id"], "observed": f"INR {stress_value:,.0f} stress impact; due in {days_to_due} days", "threshold": f"INR {overrun_limit:,.0f} / {due_limit} days", "implication": f"{row['currency']} {row['transaction_type']} of {float(row['amount']):,.2f}", "timestamp": timestamp})
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=["rank", "severity", "alert", "transaction", "observed", "threshold", "implication", "timestamp"])
    result = result.sort_values("severity", ascending=False).reset_index(drop=True)
    result["rank"] = np.arange(1, len(result) + 1)
    return result
