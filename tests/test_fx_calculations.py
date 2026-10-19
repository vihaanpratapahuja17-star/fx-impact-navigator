import pytest

from src.fx_calculations import budget_variance, hedged_settlement_cost, inr_value, scenario_impact, scenario_rate


def test_inr_conversion_known_amount():
    assert inr_value(250_000, 88) == 22_000_000


def test_payable_budget_variance_is_positive_when_cost_rises():
    assert budget_variance(250_000, 88, 85, "payable") == 750_000


def test_receivable_budget_variance_is_positive_when_receipt_falls():
    assert budget_variance(100_000, 90, 92, "receivable") == 200_000


def test_favourable_receivable_rate_has_negative_adverse_variance():
    assert budget_variance(100_000, 94, 92, "receivable") == -200_000


def test_adverse_scenario_increases_payable_cost():
    result = scenario_impact(250_000, 85, 85, 5, "payable")
    assert result["new_rate"] == pytest.approx(89.25)
    assert result["budget_variance"] == pytest.approx(1_062_500)


def test_hedge_coverage_at_zero_fifty_and_full():
    zero = hedged_settlement_cost(1000, 86, 90, 0)
    half = hedged_settlement_cost(1000, 86, 90, 50)
    full = hedged_settlement_cost(1000, 86, 90, 100)
    assert zero["total_cost"] == 90_000
    assert half["total_cost"] == 88_000
    assert full["total_cost"] == 86_000


def test_hedge_fee_is_added_to_estimated_cost():
    result = hedged_settlement_cost(1000, 86, 90, 50, 150)
    assert result["total_cost"] == 88_150


@pytest.mark.parametrize("amount,rate", [(0, 80), (100, 0), (-1, 80)])
def test_nonpositive_amount_or_rate_is_rejected(amount, rate):
    with pytest.raises(ValueError):
        inr_value(amount, rate)


def test_invalid_hedge_coverage_is_rejected():
    with pytest.raises(ValueError):
        hedged_settlement_cost(100, 80, 81, 101)


def test_scenario_rate_rejects_nonpositive_result():
    with pytest.raises(ValueError):
        scenario_rate(80, -100)
