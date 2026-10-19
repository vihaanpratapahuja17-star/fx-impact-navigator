"""Pure, testable financial calculations for foreign-currency exposures."""

from __future__ import annotations

from math import isfinite


def _positive(value: float, name: str) -> float:
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def inr_value(amount: float, rate: float) -> float:
    """Convert a foreign-currency amount at INR per one foreign-currency unit."""
    amount = _positive(amount, "amount")
    rate = _positive(rate, "rate")
    return amount * rate


def budget_variance(amount: float, actual_rate: float, budget_rate: float, transaction_type: str) -> float:
    """Return signed INR variance; positive means worse for the business.

    For payables, a higher rate costs more. For receivables, a lower rate yields
    less INR, so the sign is reversed. Zero is neutral in either case.
    """
    amount = _positive(amount, "amount")
    actual_rate = _positive(actual_rate, "actual_rate")
    budget_rate = _positive(budget_rate, "budget_rate")
    kind = transaction_type.strip().lower()
    if kind == "payable":
        return amount * (actual_rate - budget_rate)
    if kind == "receivable":
        return amount * (budget_rate - actual_rate)
    raise ValueError("transaction_type must be 'payable' or 'receivable'")


def scenario_rate(current_rate: float, movement_pct: float) -> float:
    current_rate = _positive(current_rate, "current_rate")
    rate = current_rate * (1 + float(movement_pct) / 100)
    return _positive(rate, "scenario_rate")


def scenario_impact(
    amount: float,
    current_rate: float,
    budget_rate: float,
    movement_pct: float,
    transaction_type: str = "payable",
) -> dict[str, float]:
    new_rate = scenario_rate(current_rate, movement_pct)
    budget_value = inr_value(amount, budget_rate)
    scenario_value = inr_value(amount, new_rate)
    variance = budget_variance(amount, new_rate, budget_rate, transaction_type)
    denominator = budget_value
    return {
        "new_rate": new_rate,
        "budget_value": budget_value,
        "scenario_value": scenario_value,
        "budget_variance": variance,
        "variance_pct": (variance / denominator * 100) if denominator else 0.0,
        "inr_value_change": scenario_value - inr_value(amount, current_rate),
    }


def hedged_settlement_cost(
    amount: float,
    forward_rate: float,
    settlement_spot: float,
    hedge_pct: float,
    transaction_cost: float = 0.0,
) -> dict[str, float]:
    """Estimate payable settlement cost under a simple hypothetical forward."""
    amount = _positive(amount, "amount")
    forward_rate = _positive(forward_rate, "forward_rate")
    settlement_spot = _positive(settlement_spot, "settlement_spot")
    hedge_pct = float(hedge_pct)
    transaction_cost = float(transaction_cost)
    if not 0 <= hedge_pct <= 100:
        raise ValueError("hedge_pct must be between 0 and 100")
    if not isfinite(transaction_cost) or transaction_cost < 0:
        raise ValueError("transaction_cost must be non-negative and finite")
    hedged_amount = amount * hedge_pct / 100
    unhedged_amount = amount - hedged_amount
    hedged_cost = hedged_amount * forward_rate
    unhedged_cost = unhedged_amount * settlement_spot
    total = hedged_cost + unhedged_cost + transaction_cost
    return {
        "hedged_amount": hedged_amount,
        "unhedged_amount": unhedged_amount,
        "hedged_cost": hedged_cost,
        "unhedged_cost": unhedged_cost,
        "transaction_cost": transaction_cost,
        "total_cost": total,
    }
