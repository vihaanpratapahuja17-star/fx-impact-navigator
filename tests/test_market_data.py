import pandas as pd
import sys
from types import SimpleNamespace

from src.market_data import TICKERS, fetch_history, validate_rate_csv


def test_ticker_mapping_covers_primary_currencies():
    assert TICKERS["USD"] == "INR=X"
    assert {"EUR", "GBP", "JPY"}.issubset(TICKERS)


def test_rate_csv_accepts_date_and_rate_and_sorts_rows():
    source = pd.DataFrame({"date": ["2026-02-02", "2026-02-01"], "rate": [86.0, 85.5]})
    clean, errors = validate_rate_csv(source)
    assert errors == []
    assert clean.iloc[0]["rate"] == 85.5


def test_rate_csv_rejects_bad_rates_and_duplicate_dates():
    source = pd.DataFrame({"date": ["2026-02-01", "2026-02-01"], "close": [85.0, 0]})
    _, errors = validate_rate_csv(source)
    assert any("positive numeric" in error for error in errors)
    assert any("duplicate dates" in error for error in errors)


def test_fetch_history_marks_provider_errors_unavailable(monkeypatch):
    class BrokenTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, **kwargs):
            raise TimeoutError("offline")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=BrokenTicker))
    frame, meta = fetch_history("USD")
    assert frame.empty
    assert meta["status"] == "unavailable"
    assert "TimeoutError" in meta["reason"]
