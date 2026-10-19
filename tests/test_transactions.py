import pandas as pd

from src.validation import validate_thresholds, validate_transactions


def transaction_frame():
    return pd.DataFrame([{"transaction_id": "A-1", "description": "Invoice", "currency": "USD", "amount": 1000, "transaction_type": "payable", "invoice_date": "2026-10-01", "due_date": "2026-11-01", "budget_rate": 85}])


def test_transaction_csv_validates_and_fills_optional_columns():
    clean, errors = validate_transactions(transaction_frame())
    assert errors == []
    assert clean.iloc[0]["status"] == "Open"
    assert pd.isna(clean.iloc[0]["transaction_cost"])


def test_empty_transaction_csv_is_rejected():
    clean, errors = validate_transactions(transaction_frame().iloc[0:0])
    assert clean.empty
    assert any("no transaction rows" in error for error in errors)


def test_duplicate_transaction_id_is_rejected():
    frame = pd.concat([transaction_frame(), transaction_frame()], ignore_index=True)
    _, errors = validate_transactions(frame)
    assert any("Duplicate transaction IDs" in error for error in errors)


def test_missing_amount_and_invalid_currency_are_rejected():
    frame = transaction_frame()
    frame.loc[0, "amount"] = None
    frame.loc[0, "currency"] = "XXX"
    _, errors = validate_transactions(frame)
    assert any("amount" in error for error in errors)
    assert any("Unsupported currencies" in error for error in errors)


def test_invalid_date_is_rejected():
    frame = transaction_frame()
    frame.loc[0, "invoice_date"] = "bad-date"
    _, errors = validate_transactions(frame)
    assert any("invalid dates" in error for error in errors)


def test_existing_transaction_ids_are_rejected():
    _, errors = validate_transactions(transaction_frame(), ["A-1"])
    assert any("already exist" in error for error in errors)


def test_threshold_validation_rejects_negative_values():
    assert validate_thresholds({"near_due_days": -1}) == ["near_due_days cannot be negative"]
