import numpy as np
import pandas as pd
import pytest

from src.risk_metrics import historical_var_cvar, return_series, stress_portfolio, volatility_summary
from src.hedging import backtest_policy


def test_return_series_uses_simple_percentage_returns():
    result = return_series(pd.Series([100, 110, 99]))
    assert result.tolist() == pytest.approx([0.10, -0.10])


def test_volatility_requires_at_least_two_returns_for_standard_deviation():
    result = volatility_summary(pd.Series([100, 101]))
    assert result["observations"] == 1
    assert result["daily_volatility"] is None


def test_rolling_volatility_is_missing_when_not_enough_observations():
    prices = pd.Series(np.linspace(90, 110, 25))
    result = volatility_summary(prices)
    assert result["rolling_20_latest"] is not None
    assert result["rolling_60_latest"] is None


def test_historical_var_and_cvar_on_known_returns():
    returns = pd.Series(np.linspace(-0.10, 0.10, 101))
    result = historical_var_cvar(returns, 1_000_000, 0.95)
    assert result["observations"] == 101
    assert result["var_inr"] == pytest.approx(90_000)
    assert result["cvar_inr"] == pytest.approx(95_000)


def test_var_rejects_insufficient_observations():
    with pytest.raises(ValueError, match="20 return observations"):
        historical_var_cvar(pd.Series([0.01] * 19), 100_000)


def test_stress_portfolio_combines_currency_shocks():
    exposure = pd.DataFrame({"currency": ["USD", "EUR"], "net_payable_inr": [1_000_000, -200_000]})
    result = stress_portfolio(exposure, {"USD": 5, "EUR": -3})
    assert result["cash_requirement_change_inr"].tolist() == pytest.approx([50_000, 6_000])


def test_backtest_uses_only_the_preceding_close_as_assumed_forward():
    rates = pd.Series([80.0, 82.0, 81.0], index=pd.date_range("2026-01-01", periods=3))
    result = backtest_policy(rates, amount=100, budget_rate=80, coverage_pct=50)
    assert result["assumed_forward"].tolist() == [80.0, 82.0]
    assert result["spot"].tolist() == [82.0, 81.0]
