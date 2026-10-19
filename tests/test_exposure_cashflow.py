from datetime import date

import pandas as pd

from src.cash_flow import forecast
from src.exposure_manager import enrich_transactions, exposure_by_currency, potential_offsets


def sample():
    return pd.DataFrame([
        {"transaction_id": "P1", "description": "Payable", "counterparty": "A", "currency": "USD", "amount": 1000, "transaction_type": "payable", "invoice_date": date(2026, 10, 1), "due_date": date(2026, 11, 1), "budget_rate": 85, "settlement_rate": None, "status": "Open", "category": "Imports", "notes": None, "hedge_pct": 0, "forward_rate": None, "transaction_cost": 0},
        {"transaction_id": "R1", "description": "Receivable", "counterparty": "B", "currency": "USD", "amount": 400, "transaction_type": "receivable", "invoice_date": date(2026, 10, 2), "due_date": date(2026, 11, 2), "budget_rate": 85, "settlement_rate": None, "status": "Open", "category": "Exports", "notes": None, "hedge_pct": 0, "forward_rate": None, "transaction_cost": 0},
    ])


def test_currency_aggregation_keeps_gross_and_net_separate():
    enriched = enrich_transactions(sample(), {"USD": 90}, today=date(2026, 10, 19))
    result = exposure_by_currency(enriched).iloc[0]
    assert result["payables_fc"] == 1000
    assert result["receivables_fc"] == 400
    assert result["net_payable_fc"] == 600
    assert result["net_payable_inr"] == 54_000


def test_cashflow_groups_by_date_currency_and_type():
    tx = sample()
    result = forecast(tx, {"USD": 90}, date(2026, 11, 1), date(2026, 11, 5))
    assert len(result) == 2
    assert set(result["transaction_type"]) == {"payable", "receivable"}
    assert result.loc[result["transaction_type"] == "payable", "estimated_inr"].iloc[0] == 90_000
    assert result.loc[result["transaction_type"] == "receivable", "estimated_inr"].iloc[0] == -36_000


def test_natural_offsets_are_opportunities_by_maturity_bucket():
    enriched = enrich_transactions(sample(), {"USD": 90}, today=date(2026, 10, 19))
    result = potential_offsets(enriched, 30)
    row = result.iloc[0]
    assert row["potential_offset_fc"] == 400
    assert row["residual_payable_fc"] == 600


def test_forecast_rejects_reversed_date_range():
    try:
        forecast(sample(), {"USD": 90}, date(2026, 12, 1), date(2026, 11, 1))
    except ValueError as exc:
        assert "after" in str(exc)
    else:
        raise AssertionError("Expected an invalid date range to be rejected")
