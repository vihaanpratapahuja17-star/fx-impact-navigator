"""SQLite persistence for local academic-prototype transaction data."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from .validation import TRANSACTION_COLUMNS, validate_transactions


def database_path() -> Path:
    configured = os.getenv("FXN_DB_PATH")
    path = Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1] / "data" / "fx_navigator.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY, description TEXT NOT NULL, counterparty TEXT,
            currency TEXT NOT NULL, amount REAL NOT NULL, transaction_type TEXT NOT NULL,
            invoice_date TEXT NOT NULL, due_date TEXT NOT NULL, budget_rate REAL NOT NULL,
            settlement_rate REAL, status TEXT NOT NULL DEFAULT 'Open', category TEXT,
            notes TEXT, hedge_pct REAL, forward_rate REAL, transaction_cost REAL
        )""")
        db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def load_transactions() -> pd.DataFrame:
    initialize()
    with connect() as db:
        frame = pd.read_sql_query("SELECT * FROM transactions ORDER BY due_date, transaction_id", db)
    if not frame.empty:
        for column in ("invoice_date", "due_date"):
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
    return frame.reindex(columns=TRANSACTION_COLUMNS)


def add_transaction(row: dict) -> None:
    initialize()
    clean = {key: row.get(key) for key in TRANSACTION_COLUMNS}
    clean["invoice_date"] = str(clean["invoice_date"])
    clean["due_date"] = str(clean["due_date"])
    with connect() as db:
        db.execute(
            "INSERT INTO transactions (" + ",".join(TRANSACTION_COLUMNS) + ") VALUES (" + ",".join("?" for _ in TRANSACTION_COLUMNS) + ")",
            tuple(clean[key] for key in TRANSACTION_COLUMNS),
        )


def update_transaction(transaction_id: str, row: dict) -> None:
    clean = {key: row.get(key) for key in TRANSACTION_COLUMNS}
    clean["invoice_date"] = str(clean["invoice_date"])
    clean["due_date"] = str(clean["due_date"])
    fields = [key for key in TRANSACTION_COLUMNS if key != "transaction_id"]
    with connect() as db:
        db.execute("UPDATE transactions SET " + ",".join(f"{key} = ?" for key in fields) + " WHERE transaction_id = ?", tuple(clean[key] for key in fields) + (transaction_id,))


def delete_transaction(transaction_id: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id,))


def import_transactions(data: pd.DataFrame) -> tuple[int, list[str]]:
    existing = load_transactions()
    normalized, errors = validate_transactions(data, existing.get("transaction_id", pd.Series(dtype=str)).tolist())
    if errors:
        return 0, errors
    if normalized.empty:
        return 0, ["No valid transaction rows were found"]
    for _, row in normalized.iterrows():
        add_transaction(row.to_dict())
    return len(normalized), []


def export_transactions() -> bytes:
    return load_transactions().to_csv(index=False).encode("utf-8")


def get_setting(key: str, default=None):
    initialize()
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with connect() as db:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))


def clear_transactions() -> None:
    with connect() as db:
        db.execute("DELETE FROM transactions")
