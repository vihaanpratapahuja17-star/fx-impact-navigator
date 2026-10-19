"""FX Impact Navigator — interactive treasury analytics prototype."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from ui import views
from src import exposure_manager, market_data, persistence, risk_metrics

st.set_page_config(page_title="FX Impact Navigator", page_icon="↗", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --ink:#12314A; --teal:#12A68A; --muted:#637789; --line:#E2E9EE; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--ink); }
h1,h2,h3 { font-family:'Manrope','DM Sans',sans-serif; letter-spacing:-.025em; color:var(--ink); }
h1 { font-size:2.1rem; font-weight:800; margin-bottom:.15rem; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#F2F7F8 0%,#F7F9FA 100%); border-right:1px solid var(--line); }
[data-testid="stMetric"] { background:white; padding:1rem 1.05rem; border:1px solid var(--line); border-radius:12px; box-shadow:0 2px 8px rgba(18,49,74,.035); }
[data-testid="stMetricLabel"] { color:var(--muted); font-weight:600; }
div[data-testid="stForm"] { background:#FBFCFD; border:1px solid var(--line); padding:1rem; border-radius:12px; }
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] { background:#12314A; border:0; border-radius:8px; color:white; }
div.stButton > button { border-radius:8px; }
.app-brand { font-family:'Manrope',sans-serif; font-size:1.15rem; font-weight:800; color:#12314A; line-height:1.15; }
.app-tag { font-size:.72rem; color:#637789; margin-top:.25rem; margin-bottom:1rem; }
[data-testid="stCaptionContainer"] { color:#637789; }
</style>
""", unsafe_allow_html=True)

DEFAULT_SETTINGS = {
    "business_name": "Business",
    "watchlist": ["USD", "EUR", "GBP", "JPY"],
    "lookback": "1 year",
    "stress_pct": 5.0,
    "default_hedge_pct": 50,
    "precision": 4,
    "maturity_bucket_days": 30,
    "manual_rates": {},
    "thresholds": {"movement_pct": 5.0, "volatility_pct": 2.0, "exposure_limit_inr": 1_000_000, "overrun_inr": 250_000, "near_due_days": 14},
}


@st.cache_data(ttl=900, show_spinner=False)
def load_history(currency: str, period: str):
    return market_data.fetch_history(currency, period)


def history_for_app(currency: str, period: str):
    """Prefer a validated user/evaluator series; otherwise query Yahoo Finance."""
    currency = str(currency).upper()
    uploaded = st.session_state.get("uploaded_market_data", {}).get(currency)
    if uploaded is not None and not uploaded.empty:
        periods_months = {"1mo": 1, "3mo": 3, "6mo": 6, "1y": 12, "3y": 36, "5y": 60}
        months = periods_months.get(period)
        frame = uploaded.copy()
        if months:
            cutoff = frame["date"].max() - pd.DateOffset(months=months)
            frame = frame[frame["date"] >= cutoff].reset_index(drop=True)
        observation_at = pd.Timestamp(frame.iloc[-1]["date"]).isoformat() + "Z" if not frame.empty else None
        meta = {"status": "uploaded", "provider": "User-supplied CSV", "ticker": None, "observation_at": observation_at, "retrieved_at": "Loaded from user-supplied file", "interval": "as supplied"}
        return frame, meta
    return load_history(currency, period)


def main():
    persistence.initialize()
    if "settings" not in st.session_state:
        saved = persistence.get_setting("app_settings", {}) or {}
        merged = {**DEFAULT_SETTINGS, **saved}
        merged["thresholds"] = {**DEFAULT_SETTINGS["thresholds"], **saved.get("thresholds", {})}
        st.session_state["settings"] = merged
    settings = st.session_state["settings"]
    transactions = persistence.load_transactions()
    currencies = sorted(set(transactions["currency"].dropna().astype(str).str.upper())) if not transactions.empty else []
    currencies = sorted(set(currencies + settings.get("watchlist", [])))
    history_by_currency = {}
    quote_meta = {}
    rates = {c: float(r) for c, r in settings.get("manual_rates", {}).items() if r and float(r) > 0}
    for currency in currencies:
        frame, meta = history_for_app(currency, "1mo")
        history_by_currency[currency] = frame
        quote_meta[currency] = meta
        if currency not in rates and not frame.empty:
            rates[currency] = float(frame.iloc[-1]["rate"])
    enriched = exposure_manager.enrich_transactions(
        transactions,
        rates,
        stress_pct=float(settings.get("stress_pct", 5.0)),
        risk_limit_inr=float(settings.get("thresholds", {}).get("overrun_inr", 250_000)),
        near_due_days=int(settings.get("thresholds", {}).get("near_due_days", 14)),
    )
    movements, vol = {}, {}
    for currency, frame in history_by_currency.items():
        if len(frame) >= 2:
            movements[currency] = float(frame.iloc[-1]["rate"] / frame.iloc[-2]["rate"] - 1) * 100
            summary = risk_metrics.volatility_summary(frame["rate"])
            if summary["rolling_20_latest"] is not None:
                vol[currency] = summary["rolling_20_latest"] * 100
    alerts = risk_metrics.build_alerts(enriched, movements, vol, settings.get("thresholds", {}), __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="minutes"))
    ctx = {
        "transactions": transactions,
        "enriched": enriched,
        "rates": rates,
        "quote_meta": quote_meta,
        "history_loader": history_for_app,
        "settings": settings,
        "alerts": alerts,
    }

    st.sidebar.markdown('<div class="app-brand">FX IMPACT<br>NAVIGATOR</div><div class="app-tag">CURRENCY RISK · CASH FLOW · PROFITABILITY</div>', unsafe_allow_html=True)
    st.sidebar.caption(f"{settings.get('business_name', 'Business')} · reporting currency INR")
    page_names = [
        "Executive Dashboard", "Live FX Market Monitor", "Exposure Manager", "Scenario Simulator",
        "Hedging Strategy Lab", "Risk Analytics", "Cash-Flow Forecast", "AI Treasury Analyst",
        "Data & Methodology", "Settings & Export",
    ]
    selection = st.sidebar.radio("NAVIGATION", page_names, label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(f"{len(transactions)} transaction record(s) · {len(rates)} rate(s) available")
    st.sidebar.caption("Academic decision-support prototype · not financial advice")

    dispatch = {
        "Executive Dashboard": views.dashboard,
        "Live FX Market Monitor": views.market_monitor,
        "Exposure Manager": views.exposure_manager_page,
        "Scenario Simulator": views.scenario_simulator,
        "Hedging Strategy Lab": views.hedging_lab,
        "Risk Analytics": views.risk_analytics,
        "Cash-Flow Forecast": views.cash_flow_page,
        "AI Treasury Analyst": views.analyst_page,
        "Data & Methodology": views.methodology_page,
        "Settings & Export": views.settings_page,
    }
    dispatch[selection](ctx)
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.caption("FX Impact Navigator · Reference data can be delayed or unavailable. Transaction estimates use entered assumptions.")


if __name__ == "__main__":
    main()
