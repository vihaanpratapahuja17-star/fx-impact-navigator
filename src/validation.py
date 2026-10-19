"""Input validation and CSV normalization."""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

SUPPORTED_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "SGD", "NZD", "CNY")
TRANSACTION_COLUMNS = [
    "transaction_id", "description", "counterparty", "currency", "amount",
    "transaction_type", "invoice_date", "due_date", "budget_rate",
    "settlement_rate", "status", "category", "notes", "hedge_pct",
    "forward_rate", "transaction_cost",
]
REQUIRED_COLUMNS = ["transaction_id", "description", "currency", "amount", "transaction_type", "invoice_date", "due_date", "budget_rate"]


def validate_thresholds(thresholds: dict[str, float]) -> list[str]:
    errors: list[str] = []
    for key, value in thresholds.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric")
            continue
        if number < 0:
            errors.append(f"{key} cannot be negative")
    if "near_due_days" in thresholds and float(thresholds["near_due_days"]) > 365:
        errors.append("near_due_days must be 365 or less")
    return errors


def validate_transactions(data: pd.DataFrame, existing_ids: Iterable[str] = ()) -> tuple[pd.DataFrame, list[str]]:
    """Normalize a transaction dataframe and return all actionable errors."""
    frame = data.copy()
    errors: list[str] = []
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        return frame, ["Missing required columns: " + ", ".join(missing_columns)]
    for column in TRANSACTION_COLUMNS:
        if column not in frame:
            frame[column] = None
    frame = frame[TRANSACTION_COLUMNS]
    if frame.empty:
        return frame, ["The uploaded file has no transaction rows"]

    for column in REQUIRED_COLUMNS:
        if frame[column].isna().any() or (frame[column].astype(str).str.strip() == "").any():
            errors.append(f"{column} contains missing values")

    frame["transaction_id"] = frame["transaction_id"].astype(str).str.strip()
    duplicate_ids = frame.loc[frame["transaction_id"].duplicated(keep=False), "transaction_id"].unique().tolist()
    if duplicate_ids:
        errors.append("Duplicate transaction IDs in upload: " + ", ".join(duplicate_ids))
    overlap = sorted(set(frame["transaction_id"]) & {str(x) for x in existing_ids})
    if overlap:
        errors.append("Transaction IDs already exist: " + ", ".join(overlap))

    frame["currency"] = frame["currency"].astype(str).str.upper().str.strip()
    invalid_currency = sorted(set(frame["currency"]) - set(SUPPORTED_CURRENCIES))
    if invalid_currency:
        errors.append("Unsupported currencies: " + ", ".join(invalid_currency))
    frame["transaction_type"] = frame["transaction_type"].astype(str).str.lower().str.strip()
    invalid_type = sorted(set(frame["transaction_type"]) - {"payable", "receivable"})
    if invalid_type:
        errors.append("transaction_type must be payable or receivable")

    for column in ("amount", "budget_rate", "settlement_rate", "hedge_pct", "forward_rate", "transaction_cost"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("amount", "budget_rate"):
        if frame[column].isna().any() or (frame[column] <= 0).any():
            errors.append(f"{column} must contain positive numbers")
    for column in ("settlement_rate", "forward_rate"):
        if (frame[column].dropna() <= 0).any():
            errors.append(f"{column} must be positive when provided")
    if ((frame["hedge_pct"].dropna() < 0) | (frame["hedge_pct"].dropna() > 100)).any():
        errors.append("hedge_pct must be between 0 and 100")
    if (frame["transaction_cost"].dropna() < 0).any():
        errors.append("transaction_cost cannot be negative")

    for column in ("invoice_date", "due_date"):
        parsed = pd.to_datetime(frame[column], errors="coerce").dt.date
        if parsed.isna().any():
            errors.append(f"{column} contains invalid dates")
        frame[column] = parsed
    valid_dates = frame["invoice_date"].notna() & frame["due_date"].notna()
    if (frame.loc[valid_dates, "due_date"] < frame.loc[valid_dates, "invoice_date"]).any():
        errors.append("due_date cannot be earlier than invoice_date")

    frame["status"] = frame["status"].fillna("Open").astype(str).str.strip().str.title()
    invalid_status = sorted(set(frame["status"]) - {"Open", "Settled", "Cancelled"})
    if invalid_status:
        errors.append("status must be Open, Settled or Cancelled")
    settled_without_rate = (frame["status"] == "Settled") & frame["settlement_rate"].isna()
    if settled_without_rate.any():
        errors.append("settlement_rate is required when status is Settled")
    return frame, errors


def transaction_from_form(values: dict) -> dict:
    row = {key: values.get(key) for key in TRANSACTION_COLUMNS}
    normalized, errors = validate_transactions(pd.DataFrame([row]))
    if errors:
        raise ValueError("; ".join(errors))
    return normalized.iloc[0].to_dict()


def valid_as_of(value: date | None) -> bool:
    return value is not None
