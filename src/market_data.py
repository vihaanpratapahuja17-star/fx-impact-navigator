"""Yahoo Finance FX history adapter with explicit freshness and manual fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

TICKERS = {
    "USD": "INR=X", "EUR": "EURINR=X", "GBP": "GBPINR=X", "JPY": "JPYINR=X",
    "CHF": "CHFINR=X", "AUD": "AUDINR=X", "CAD": "CADINR=X", "SGD": "SGDINR=X",
    "NZD": "NZDINR=X", "CNY": "CNYINR=X",
}
PERIODS = {"1 month": "1mo", "3 months": "3mo", "6 months": "6mo", "1 year": "1y", "3 years": "3y", "5 years": "5y"}


def fetch_history(currency: str, period: str = "1y") -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch daily observations; failures return an empty frame and a warning."""
    currency = str(currency).upper()
    ticker = TICKERS.get(currency)
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not ticker:
        return pd.DataFrame(columns=["date", "rate"]), {"status": "unavailable", "reason": "No ticker mapping configured", "ticker": None, "retrieved_at": retrieved}
    try:
        import yfinance as yf

        raw = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False, actions=False, timeout=12)
        if raw is None or raw.empty or "Close" not in raw:
            return pd.DataFrame(columns=["date", "rate"]), {"status": "unavailable", "reason": "Provider returned no observations", "ticker": ticker, "retrieved_at": retrieved}
        rates = raw["Close"].dropna().astype(float)
        frame = rates.rename("rate").to_frame().reset_index()
        frame.columns = ["date", "rate"]
        frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert(None)
        frame = frame.drop_duplicates("date").sort_values("date").reset_index(drop=True)
        frame = frame[frame["rate"] > 0]
        if frame.empty:
            return pd.DataFrame(columns=["date", "rate"]), {"status": "unavailable", "reason": "Provider returned no positive rates", "ticker": ticker, "retrieved_at": retrieved}
        observation_at = pd.Timestamp(frame.iloc[-1]["date"]).isoformat() + "Z"
        return frame, {"status": "retrieved", "ticker": ticker, "provider": "Yahoo Finance via yfinance", "observation_at": observation_at, "retrieved_at": retrieved, "interval": "daily"}
    except Exception as exc:  # provider and network failures must not crash the app
        return pd.DataFrame(columns=["date", "rate"]), {"status": "unavailable", "reason": f"Market data request failed: {type(exc).__name__}", "ticker": ticker, "retrieved_at": retrieved}


def latest_quote(frame: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return {**meta, "rate": None}
    return {**meta, "rate": float(frame.iloc[-1]["rate"])}


def validate_rate_csv(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Accept a user-provided historical series with date and rate columns."""
    frame = data.copy()
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    if "date" not in frame.columns:
        return pd.DataFrame(columns=["date", "rate"]), ["CSV must include a date column"]
    rate_column = "rate" if "rate" in frame.columns else "close" if "close" in frame.columns else None
    if rate_column is None:
        return pd.DataFrame(columns=["date", "rate"]), ["CSV must include a rate or close column"]
    clean = frame[["date", rate_column]].rename(columns={rate_column: "rate"})
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce", utc=True).dt.tz_convert(None)
    clean["rate"] = pd.to_numeric(clean["rate"], errors="coerce")
    errors = []
    if clean["date"].isna().any(): errors.append("CSV contains invalid dates")
    if clean["rate"].isna().any() or (~clean["rate"].map(lambda x: pd.notna(x) and x > 0)).any(): errors.append("Rates must be positive numeric values")
    if clean["date"].duplicated().any(): errors.append("CSV contains duplicate dates")
    clean = clean.dropna(subset=["date", "rate"]).sort_values("date").reset_index(drop=True)
    if len(clean) < 2: errors.append("At least two valid observations are required")
    return clean, errors


def rate_for_currency(currency: str, manual_rates: dict[str, float], history_by_currency: dict[str, pd.DataFrame]) -> tuple[float | None, str]:
    manual = manual_rates.get(str(currency).upper())
    if manual is not None and float(manual) > 0:
        return float(manual), "manual"
    frame = history_by_currency.get(str(currency).upper())
    if frame is not None and not frame.empty:
        return float(frame.iloc[-1]["rate"]), "market data"
    return None, "unavailable"
