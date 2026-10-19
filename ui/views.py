"""Streamlit page renderers. UI controls call the same calculation modules as tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import cash_flow, exposure_manager, hedging, market_data, risk_metrics, scenario_engine
from src.fx_calculations import scenario_rate
from src.persistence import add_transaction, delete_transaction, export_transactions, import_transactions, set_setting, update_transaction
from src.reporting import management_report
from src.validation import SUPPORTED_CURRENCIES, TRANSACTION_COLUMNS, transaction_from_form

ROOT = Path(__file__).resolve().parents[1]
NAVY = "#12314A"
TEAL = "#12A68A"
MUTED = "#5F7182"


def _money(value, currency="INR") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{currency} {float(value):,.0f}"


def _rate(value) -> str:
    return "—" if value is None or pd.isna(value) else f"₹{float(value):,.4f}"


def _style(fig, height=330):
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=12, r=12, t=38, b=12), font=dict(family="Inter, Arial, sans-serif", color=NAVY), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showgrid=False, linecolor="#DCE4E9")
    fig.update_yaxes(gridcolor="#ECF1F4", zerolinecolor="#DCE4E9")
    return fig


def _market_frame(ctx, currency, period=None):
    period = period or ctx["settings"].get("lookback", "1 year")
    return ctx["history_loader"](currency, market_data.PERIODS.get(period, "1y"))


def _with_rates(ctx):
    tx = ctx["transactions"]
    currencies = sorted(set(tx["currency"].dropna().astype(str).str.upper())) if not tx.empty else []
    rates = dict(ctx["settings"].get("manual_rates", {}))
    for currency in currencies:
        if currency in rates and rates[currency] > 0:
            continue
        frame, meta = _market_frame(ctx, currency, "1 month")
        quote = market_data.latest_quote(frame, meta)
        if quote.get("rate"):
            rates[currency] = quote["rate"]
    return rates


def dashboard(ctx):
    st.title("Executive dashboard")
    st.caption("A working view of open currency exposure, upcoming cash flows and configured risk limits.")
    frame = ctx["enriched"].copy()
    if frame.empty:
        st.info("Add invoices or load the illustrative sample from Exposure Manager to see your business exposure.")
        st.metric("Open transactions", "0")
        return

    c1, c2, c3, c4 = st.columns([1.1, 1.1, 1, 1.2])
    currencies = ["All"] + sorted(frame["currency"].dropna().unique().tolist())
    currency = c1.selectbox("Currency", currencies, key="dash_currency")
    kinds = ["All", "payable", "receivable"]
    kind = c2.selectbox("Transaction type", kinds, key="dash_type")
    cats = ["All"] + sorted([str(x) for x in frame["category"].dropna().unique() if str(x).strip()])
    category = c3.selectbox("Business unit", cats, key="dash_category")
    statuses = ["All"] + sorted(frame["risk_status"].dropna().unique().tolist())
    status = c4.selectbox("Risk status", statuses, key="dash_status")
    if currency != "All": frame = frame[frame["currency"] == currency]
    if kind != "All": frame = frame[frame["transaction_type"] == kind]
    if category != "All": frame = frame[frame["category"].astype(str) == category]
    if status != "All": frame = frame[frame["risk_status"] == status]
    if frame.empty:
        st.info("No transactions match the selected filters.")
        return

    active = frame[~frame["status"].astype(str).str.lower().isin(["settled", "cancelled"])]
    payables = active[active["transaction_type"] == "payable"]
    receivables = active[active["transaction_type"] == "receivable"]
    total_pay = payables["reference_inr"].fillna(payables["budget_inr"]).sum()
    total_rec = receivables["reference_inr"].fillna(receivables["budget_inr"]).sum()
    near = payables[payables["days_to_due"].between(0, 30)]["reference_inr"].fillna(payables[payables["days_to_due"].between(0, 30)]["budget_inr"]).sum()
    adverse = active["stress_impact_inr"].sum()
    overdue_count = int((active["days_to_due"] < 0).sum())
    metrics = st.columns(5)
    metrics[0].metric("Open payables", _money(total_pay), help="Reference-rate estimate; budget-rate proxy is used where market data is unavailable.")
    metrics[1].metric("Open receivables", _money(total_rec))
    metrics[2].metric("Net INR exposure", _money(total_pay - total_rec), help="Positive means net payable based on estimated INR values.")
    metrics[3].metric("Payments due in 30 days", _money(near))
    metrics[4].metric("Adverse stress impact", _money(adverse), help=f"Configured {ctx['settings'].get('stress_pct', 5):g}% adverse currency movement; scenario, not forecast.")

    left, right = st.columns(2)
    exposure = exposure_manager.exposure_by_currency(active)
    if not exposure.empty:
        chart_data = exposure.melt(id_vars="currency", value_vars=["payables_inr", "receivables_inr"], var_name="type", value_name="inr")
        fig = px.bar(chart_data, x="currency", y="inr", color="type", barmode="group", color_discrete_sequence=[NAVY, TEAL], title="Gross exposure by currency")
        left.plotly_chart(_style(fig), width="stretch")
    due = active.copy()
    due["due_date"] = pd.to_datetime(due["due_date"])
    due["signed_inr"] = np.where(due["transaction_type"] == "payable", due["reference_inr"].fillna(due["budget_inr"]), -due["reference_inr"].fillna(due["budget_inr"]))
    due_daily = due.groupby(["due_date", "transaction_type"], as_index=False)["signed_inr"].sum()
    fig2 = px.bar(due_daily, x="due_date", y="signed_inr", color="transaction_type", color_discrete_sequence=[TEAL, NAVY], title="Estimated cash flows by due date")
    fig2.update_yaxes(title="INR requirement (+) / receipt (−)")
    right.plotly_chart(_style(fig2), width="stretch")

    st.subheader("Items to investigate")
    attention = active[active["risk_status"].isin(["Overdue", "Due soon", "Review"])].sort_values(["stress_impact_inr", "days_to_due"], ascending=[False, True])
    if attention.empty:
        st.success("No open transactions currently breach the configured date or exposure thresholds.")
    else:
        st.dataframe(attention[["transaction_id", "description", "currency", "transaction_type", "due_date", "days_to_due", "stress_impact_inr", "risk_status"]], hide_index=True, width="stretch")
    quote_times = [str(v.get("observation_at")) for v in ctx["quote_meta"].values() if v.get("observation_at")]
    st.caption("Market observation: " + (", ".join(quote_times[:3]) if quote_times else "No market observations loaded. Manual rates or budget-rate proxies may be in use."))


def market_monitor(ctx):
    st.title("Live FX market monitor")
    st.caption("Daily reference observations from Yahoo Finance where available. A quote may be delayed or unavailable; it is not an executable bank rate.")
    currency = st.selectbox("Currency pair", SUPPORTED_CURRENCIES, index=0, format_func=lambda code: f"{code}/INR", key="market_currency")
    period = st.selectbox("History window", list(market_data.PERIODS), index=3, key="market_period")
    with st.expander("Load an evaluator-supplied or user-supplied rate CSV"):
        st.caption("Accepted columns: date and rate (or close). The supplied observations replace provider history for this currency during the current local session.")
        uploaded = st.file_uploader("Historical rate CSV", type=["csv"], key=f"rate_csv_{currency}")
        uploaded_series = st.session_state.setdefault("uploaded_market_data", {})
        uploaded_signatures = st.session_state.setdefault("uploaded_market_signatures", {})
        if uploaded is not None:
            signature = f"{uploaded.name}:{uploaded.size}"
            if uploaded_signatures.get(currency) != signature:
                try:
                    clean, errors = market_data.validate_rate_csv(pd.read_csv(uploaded))
                    if errors:
                        st.error("CSV not loaded: " + "; ".join(errors))
                    else:
                        uploaded_series[currency] = clean
                        uploaded_signatures[currency] = signature
                        st.success(f"Loaded {len(clean)} daily observations for {currency}/INR.")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Could not read this CSV: {exc}")
        if currency in uploaded_series:
            st.success(f"A user-supplied series is active for {currency}/INR ({len(uploaded_series[currency])} observations).")
            if st.button("Remove uploaded series", key=f"remove_rate_series_{currency}"):
                uploaded_series.pop(currency, None)
                uploaded_signatures.pop(currency, None)
                st.rerun()
    if st.button("Refresh market data", type="secondary"):
        st.cache_data.clear()
        st.rerun()
    frame, meta = _market_frame(ctx, currency, period)
    manual = ctx["settings"].get("manual_rates", {}).get(currency)
    quote = market_data.latest_quote(frame, meta)
    selected_rate = manual if manual else quote.get("rate")
    cols = st.columns(4)
    cols[0].metric("INR per 1 " + currency, _rate(selected_rate), help="Manual override takes precedence when configured.")
    if len(frame) >= 2:
        delta = float(frame.iloc[-1]["rate"] / frame.iloc[-2]["rate"] - 1) * 100
        cols[1].metric("Latest daily move", f"{delta:+.2f}%")
        cols[2].metric("Window high", _rate(frame["rate"].max()))
        cols[3].metric("Window low", _rate(frame["rate"].min()))
        fig = px.line(frame, x="date", y="rate", title=f"{currency}/INR daily close observations", color_discrete_sequence=[TEAL])
        st.plotly_chart(_style(fig, 360), width="stretch")
        returns = risk_metrics.return_series(frame["rate"])
        if not returns.empty:
            returns_frame = pd.DataFrame({"date": frame["date"].iloc[1:].values, "return_pct": returns.values * 100})
            fig2 = px.bar(returns_frame, x="date", y="return_pct", title="Daily percentage returns", color_discrete_sequence=[NAVY])
            st.plotly_chart(_style(fig2, 260), width="stretch")
    else:
        st.warning(meta.get("reason", "Not enough observations for the selected period."))
    if meta.get("status") == "retrieved":
        st.caption(f"Provider: {meta.get('provider')} · ticker {meta.get('ticker')} · observation {meta.get('observation_at')} · retrieved {meta.get('retrieved_at')} · daily interval")
    elif meta.get("status") == "uploaded":
        st.caption(f"Source: {meta.get('provider')} · latest supplied observation {meta.get('observation_at')} · timestamp reflects data row, not retrieval time")
    else:
        st.caption(f"Market-data status: unavailable · {meta.get('retrieved_at', 'timestamp not available')}")
    st.divider()
    st.subheader("Manual reference-rate override")
    st.caption("Use an explicitly supplied rate to continue analysis when the provider is unavailable. This value is labeled manual throughout the app.")
    with st.form("manual_quote_form"):
        current_manual = float(ctx["settings"].get("manual_rates", {}).get(currency, 0.0))
        manual_input = st.number_input(f"Manual {currency}/INR rate", min_value=0.0, value=current_manual, step=0.01, format="%.4f")
        clear = st.checkbox("Clear manual override", key="clear_manual")
        if st.form_submit_button("Save rate override"):
            settings = dict(ctx["settings"])
            rates = dict(settings.get("manual_rates", {}))
            if clear:
                rates.pop(currency, None)
            elif manual_input > 0:
                rates[currency] = manual_input
            else:
                st.error("Enter a positive rate or choose clear override.")
                return
            settings["manual_rates"] = rates
            set_setting("app_settings", settings)
            st.session_state["settings"] = settings
            st.success("Rate setting saved.")
            st.rerun()
    if not frame.empty:
        st.download_button("Download historical observations CSV", frame.to_csv(index=False).encode(), file_name=f"{currency.lower()}_inr_history.csv", mime="text/csv")


def exposure_manager_page(ctx):
    st.title("Exposure and invoice manager")
    st.caption("Transactions are stored in a local SQLite database. Do not enter confidential company data into a publicly hosted demonstration app.")
    tabs = st.tabs(["Register", "Add transaction", "Edit or delete", "CSV import"])
    with tabs[0]:
        frame = ctx["enriched"].copy()
        if frame.empty:
            st.info("Your register is empty. Add a record or load the clearly illustrative sample file.")
        else:
            search = st.text_input("Search ID, description or counterparty", key="txn_search").strip().lower()
            if search:
                mask = frame[["transaction_id", "description", "counterparty"]].fillna("").astype(str).apply(lambda col: col.str.lower().str.contains(search, regex=False)).any(axis=1)
                frame = frame[mask]
            st.dataframe(frame, hide_index=True, width="stretch", column_config={"budget_inr": st.column_config.NumberColumn("Budget INR", format="₹%.0f"), "reference_inr": st.column_config.NumberColumn("Reference INR", format="₹%.0f"), "variance_inr": st.column_config.NumberColumn("Variance INR · + adverse", format="₹%.0f"), "stress_impact_inr": st.column_config.NumberColumn("Stress impact INR", format="₹%.0f")})
            st.download_button("Export transaction register CSV", export_transactions(), file_name="fx_transactions.csv", mime="text/csv")
        sample = (ROOT / "data" / "sample_transactions.csv").read_bytes()
        st.download_button("Download illustrative CSV template", sample, file_name="sample_transactions_illustrative.csv", mime="text/csv")
        if st.button("Import illustrative sample transactions"):
            sample_frame = pd.read_csv(ROOT / "data" / "sample_transactions.csv")
            count, errors = import_transactions(sample_frame)
            if errors: st.error("Import not completed: " + "; ".join(errors))
            else: st.success(f"Imported {count} illustrative records."); st.rerun()
    with tabs[1]:
        with st.form("add_transaction_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            txn_id = c1.text_input("Transaction ID", value="", placeholder="e.g. INV-2026-001")
            description = c2.text_input("Description", placeholder="Supplier invoice")
            c1, c2, c3 = st.columns(3)
            currency = c1.selectbox("Currency", SUPPORTED_CURRENCIES, key="add_currency")
            txn_type = c2.selectbox("Type", ["payable", "receivable"], format_func=str.title)
            amount = c3.number_input("Foreign-currency amount", min_value=0.0, value=0.0, step=1000.0)
            c1, c2 = st.columns(2)
            invoice_date = c1.date_input("Invoice date", value=date.today())
            due_date = c2.date_input("Due date", value=date.today() + timedelta(days=30))
            c1, c2, c3 = st.columns(3)
            budget_rate = c1.number_input("Budget rate · INR per currency unit", min_value=0.0, value=0.0, step=0.1, format="%.4f")
            settle = c2.number_input("Settlement rate, if settled", min_value=0.0, value=0.0, step=0.1, format="%.4f")
            status = c3.selectbox("Status", ["Open", "Settled", "Cancelled"])
            c1, c2 = st.columns(2)
            counterparty = c1.text_input("Counterparty")
            category = c2.text_input("Business unit or category")
            c1, c2, c3 = st.columns(3)
            hedge_pct = c1.number_input("Hedge coverage %", min_value=0.0, max_value=100.0, value=0.0)
            forward_rate = c2.number_input("Assumed forward rate", min_value=0.0, value=0.0, step=0.1, format="%.4f")
            transaction_cost = c3.number_input("Hedge transaction cost INR", min_value=0.0, value=0.0, step=100.0)
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Add transaction", type="primary")
        if submitted:
            values = {"transaction_id": txn_id, "description": description, "counterparty": counterparty, "currency": currency, "amount": amount, "transaction_type": txn_type, "invoice_date": invoice_date, "due_date": due_date, "budget_rate": budget_rate, "settlement_rate": settle or None, "status": status, "category": category, "notes": notes, "hedge_pct": hedge_pct, "forward_rate": forward_rate or None, "transaction_cost": transaction_cost}
            try:
                row = transaction_from_form(values)
                add_transaction(row)
                st.success("Transaction added.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with tabs[2]:
        rows = ctx["transactions"]
        if rows.empty:
            st.info("There are no transactions to edit or delete.")
        else:
            selected = st.selectbox("Select transaction", rows["transaction_id"].astype(str).tolist())
            original = rows[rows["transaction_id"].astype(str) == selected].iloc[0].to_dict()
            with st.form("edit_transaction_form"):
                c1, c2 = st.columns(2)
                description = c1.text_input("Description", str(original.get("description", "")))
                counterparty = c2.text_input("Counterparty", str(original.get("counterparty", "") or ""))
                c1, c2, c3 = st.columns(3)
                currency = c1.selectbox("Currency", SUPPORTED_CURRENCIES, index=SUPPORTED_CURRENCIES.index(original["currency"]))
                txn_type = c2.selectbox("Type", ["payable", "receivable"], index=["payable", "receivable"].index(original["transaction_type"]))
                amount = c3.number_input("Amount", min_value=0.0, value=float(original["amount"]))
                c1, c2 = st.columns(2)
                invoice_date = c1.date_input("Invoice date", value=pd.to_datetime(original["invoice_date"]).date())
                due_date = c2.date_input("Due date", value=pd.to_datetime(original["due_date"]).date())
                c1, c2, c3 = st.columns(3)
                budget_rate = c1.number_input("Budget rate", min_value=0.0, value=float(original["budget_rate"]), format="%.4f")
                settlement_rate = c2.number_input("Settlement rate", min_value=0.0, value=float(original["settlement_rate"] or 0), format="%.4f")
                status = c3.selectbox("Status", ["Open", "Settled", "Cancelled"], index=["Open", "Settled", "Cancelled"].index(original["status"]))
                c1, c2, c3 = st.columns(3)
                hedge_pct = c1.number_input("Hedge coverage %", min_value=0.0, max_value=100.0, value=float(original.get("hedge_pct") or 0))
                forward_rate = c2.number_input("Assumed forward rate", min_value=0.0, value=float(original.get("forward_rate") or 0), format="%.4f")
                transaction_cost = c3.number_input("Hedge transaction cost INR", min_value=0.0, value=float(original.get("transaction_cost") or 0))
                category = st.text_input("Category", str(original.get("category", "") or ""))
                notes = st.text_area("Notes", str(original.get("notes", "") or ""))
                save = st.form_submit_button("Save changes", type="primary")
            if save:
                row = {**original, "description": description, "counterparty": counterparty, "currency": currency, "transaction_type": txn_type, "amount": amount, "invoice_date": invoice_date, "due_date": due_date, "budget_rate": budget_rate, "settlement_rate": settlement_rate or None, "status": status, "hedge_pct": hedge_pct, "forward_rate": forward_rate or None, "transaction_cost": transaction_cost, "category": category, "notes": notes}
                try:
                    clean = transaction_from_form(row)
                    update_transaction(selected, clean)
                    st.success("Transaction updated.")
                    st.rerun()
                except Exception as exc: st.error(str(exc))
            confirm = st.checkbox(f"Confirm deletion of {selected}")
            if st.button("Delete selected transaction", disabled=not confirm):
                delete_transaction(selected)
                st.success("Transaction deleted.")
                st.rerun()
    with tabs[3]:
        st.write("Required CSV fields: " + ", ".join(["transaction_id", "description", "currency", "amount", "transaction_type", "invoice_date", "due_date", "budget_rate"]))
        uploaded = st.file_uploader("Choose transaction CSV", type=["csv"], key="transaction_upload")
        if uploaded is not None:
            try:
                preview = pd.read_csv(uploaded)
                st.dataframe(preview.head(20), hide_index=True, width="stretch")
                if st.button("Validate and import CSV", type="primary"):
                    count, errors = import_transactions(preview)
                    if errors: st.error("Import not completed: " + "; ".join(errors))
                    else: st.success(f"Imported {count} transaction rows."); st.rerun()
            except Exception as exc: st.error(f"Could not read this CSV: {exc}")


def scenario_simulator(ctx):
    st.title("FX scenario simulator")
    st.caption("Change a reference-rate assumption to see its effect on transaction cost or receipt value. Scenario outputs are not predictions.")
    tx = ctx["transactions"]
    currency_default = tx.iloc[0]["currency"] if not tx.empty else "USD"
    currency = st.selectbox("Currency pair", SUPPORTED_CURRENCIES, index=SUPPORTED_CURRENCIES.index(currency_default), format_func=lambda code: f"{code}/INR", key="scenario_currency")
    selected = tx[tx["currency"] == currency] if not tx.empty else tx
    amount_default = float(selected.iloc[0]["amount"]) if not selected.empty else 250000.0
    budget_default = float(selected.iloc[0]["budget_rate"]) if not selected.empty else 0.0
    kind_default = str(selected.iloc[0]["transaction_type"]) if not selected.empty else "payable"
    current_default = float(ctx["rates"].get(currency, budget_default))
    cols = st.columns(4)
    amount = cols[0].number_input("Invoice amount", min_value=0.0, value=amount_default, step=1000.0, key="scenario_amount")
    current = cols[1].number_input("Current/reference rate · INR per unit", min_value=0.0, value=current_default, step=0.01, format="%.4f", key="scenario_current")
    budget = cols[2].number_input("Budget rate", min_value=0.0, value=budget_default, step=0.01, format="%.4f", key="scenario_budget")
    kind = cols[3].selectbox("Exposure type", ["payable", "receivable"], index=["payable", "receivable"].index(kind_default), format_func=str.title, key="scenario_type")
    label_to_move = {"No change": 0.0, "2% adverse": 2.0, "5% adverse": 5.0, "10% adverse": 10.0, "5% favourable": -5.0}
    move_choice = st.multiselect("Compare predefined scenarios", list(label_to_move), default=["No change", "2% adverse", "5% adverse", "10% adverse", "5% favourable"])
    custom = st.number_input("Custom exchange-rate movement (%)", min_value=-90.0, max_value=100.0, value=0.0, step=0.5)
    include_custom = st.checkbox("Include custom scenario", value=True)
    if amount <= 0 or current <= 0 or budget <= 0:
        st.info("Enter a positive amount, reference rate and budget rate to calculate scenarios.")
        return
    movements = {label: label_to_move[label] for label in move_choice}
    if include_custom: movements[f"Custom ({custom:+.1f}%)"] = custom
    results = scenario_engine.compare_scenarios(amount, current, budget, kind, movements)
    st.dataframe(results, hide_index=True, width="stretch", column_config={"new_rate": st.column_config.NumberColumn("Scenario rate", format="₹%.4f"), "scenario_value": st.column_config.NumberColumn("INR value", format="₹%.0f"), "budget_variance": st.column_config.NumberColumn("Variance vs budget · + adverse", format="₹%.0f"), "variance_pct": st.column_config.NumberColumn("Variance %", format="%.2f%%")})
    fig = px.bar(results, x="scenario", y="budget_variance", color="budget_variance", color_continuous_scale=[TEAL, "#F3B544", "#D75A5A"], title="Signed budget impact · positive is adverse")
    st.plotly_chart(_style(fig), width="stretch")
    rev = st.number_input("Expected sales or export revenue (INR, optional)", min_value=0.0, value=0.0, step=10000.0)
    costs = st.number_input("Other INR costs (optional)", min_value=0.0, value=0.0, step=10000.0)
    if rev > 0:
        adverse_rate = float(results.iloc[-1]["new_rate"])
        p = scenario_engine.profitability_change(amount, current, adverse_rate, kind, rev, costs)
        st.metric("Change in estimated profit for selected last scenario", _money(p["profit_change_inr"]))
        st.caption("Profit model includes only the supplied FX amount, revenue and other-cost assumptions.")
    st.subheader("Amount and exchange-rate sensitivity")
    min_amount = st.number_input("Heatmap low amount", min_value=1.0, value=max(1.0, amount * 0.5), step=1000.0)
    max_amount = st.number_input("Heatmap high amount", min_value=min_amount + 1, value=max(min_amount + 1, amount * 1.5), step=1000.0)
    low_rate = current * 0.9
    high_rate = current * 1.1
    amounts = np.linspace(min_amount, max_amount, 7)
    rate_values = np.linspace(low_rate, high_rate, 9)
    grid = scenario_engine.sensitivity_grid(amounts, rate_values).pivot(index="amount", columns="rate", values="inr_value")
    fig2 = go.Figure(data=go.Heatmap(x=[f"{x:.3f}" for x in grid.columns], y=[f"{x:,.0f}" for x in grid.index], z=grid.values, colorscale="Blues", colorbar=dict(title="INR")))
    fig2.update_layout(title="INR value by amount and rate", xaxis_title="INR per foreign-currency unit", yaxis_title="Foreign-currency amount")
    st.plotly_chart(_style(fig2, 360), width="stretch")
    st.download_button("Download scenario comparison CSV", results.to_csv(index=False).encode(), file_name="scenario_comparison.csv", mime="text/csv")


def hedging_lab(ctx):
    st.title("Hedging strategy lab")
    st.caption("Hypothetical forward scenario only. It does not represent a bank offer, executable contract or recommendation.")
    tx = ctx["transactions"]
    currency_default = tx.iloc[0]["currency"] if not tx.empty else "USD"
    currency = st.selectbox("Currency", SUPPORTED_CURRENCIES, index=SUPPORTED_CURRENCIES.index(currency_default), key="hedge_currency")
    selected = tx[(tx["currency"] == currency) & (tx["transaction_type"] == "payable")] if not tx.empty else tx
    amount_default = float(selected.iloc[0]["amount"]) if not selected.empty else 0.0
    budget_default = float(selected.iloc[0]["budget_rate"]) if not selected.empty else 0.0
    spot_default = float(ctx["rates"].get(currency, budget_default))
    cols = st.columns(4)
    amount = cols[0].number_input("Payable amount", min_value=0.0, value=amount_default, step=1000.0)
    spot = cols[1].number_input("Scenario settlement spot", min_value=0.0, value=spot_default, step=0.01, format="%.4f")
    forward = cols[2].number_input("Assumed forward rate (user input)", min_value=0.0, value=0.0, step=0.01, format="%.4f")
    budget = cols[3].number_input("Budget rate", min_value=0.0, value=budget_default, step=0.01, format="%.4f")
    cost = st.number_input("Total hedge transaction costs (INR)", min_value=0.0, value=0.0, step=100.0)
    movement = st.slider("Scenario spot movement from current reference rate (%)", -20.0, 20.0, 5.0, 0.5)
    if amount <= 0 or spot <= 0 or forward <= 0 or budget <= 0:
        st.info("Enter a positive payable, assumed forward rate, spot and budget rate. No forward quote is supplied by the app.")
        return
    scenario_spot = spot * (1 + movement / 100)
    levels = [0, 25, 50, 75, 100]
    custom = st.slider("Custom coverage (%)", 0, 100, int(ctx["settings"].get("default_hedge_pct", 50)))
    levels.append(custom)
    levels = sorted(set(levels))
    results = hedging.compare_hedges(amount, forward, {f"Scenario {movement:+.1f}%": scenario_spot}, budget, levels, cost)
    st.dataframe(results, hide_index=True, width="stretch", column_config={"total_cost": st.column_config.NumberColumn("Estimated settlement INR", format="₹%.0f"), "variance_from_budget": st.column_config.NumberColumn("Variance vs budget", format="₹%.0f"), "hedged_amount": st.column_config.NumberColumn("Hedged amount", format="%.2f"), "unhedged_amount": st.column_config.NumberColumn("Unhedged amount", format="%.2f")})
    fig = px.line(results, x="coverage_pct", y="total_cost", markers=True, title="Estimated settlement cost by hedge coverage", color_discrete_sequence=[NAVY])
    st.plotly_chart(_style(fig), width="stretch")
    st.info("Economics: hedging caps the covered portion at the assumed forward rate. If settlement spot later becomes more favourable than the assumed forward, that portion does not benefit. The uncovered portion remains exposed. Rates, costs, settlement conventions and contract terms must be confirmed independently.")
    history, meta = _market_frame(ctx, currency, "1 year")
    if not history.empty and len(history) >= 3:
        bt = hedging.backtest_policy(pd.Series(history["rate"].values, index=history["date"]), amount, budget, custom, cost)
        if not bt.empty:
            st.subheader("Historical one-step proxy simulation")
            st.caption("For each historical date, the prior daily close is used as a simple assumed-forward proxy. This is not a historical forward-quote test and does not support conclusions about future performance.")
            bt["date"] = pd.to_datetime(bt["date"])
            fig2 = px.line(bt, x="date", y=["unhedged_cost", "policy_cost"], title="Hypothetical costs under historical spot observations")
            st.plotly_chart(_style(fig2), width="stretch")
            st.write(f"Unhedged cost standard deviation: INR {bt['unhedged_cost'].std():,.0f}; proxy policy: INR {bt['policy_cost'].std():,.0f}.")
            st.download_button("Download backtest CSV", bt.to_csv(index=False).encode(), file_name="hedge_policy_historical_proxy.csv", mime="text/csv")
    st.download_button("Download hedge comparison CSV", results.to_csv(index=False).encode(), file_name="hedge_comparison.csv", mime="text/csv")


def risk_analytics(ctx):
    st.title("Risk analytics and early warning")
    st.caption("Historical statistics describe the selected sample and are not forecasts or maximum-loss measures.")
    currencies = sorted(set(ctx["transactions"]["currency"].astype(str))) if not ctx["transactions"].empty else list(SUPPORTED_CURRENCIES[:4])
    currency = st.selectbox("Currency", currencies, key="risk_currency")
    history, meta = _market_frame(ctx, currency, ctx["settings"].get("lookback", "1 year"))
    if len(history) >= 2:
        summary = risk_metrics.volatility_summary(history["rate"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Daily volatility", "—" if summary["daily_volatility"] is None else f"{summary['daily_volatility']*100:.2f}%")
        c2.metric("Annualized volatility", "—" if summary["annualized_volatility"] is None else f"{summary['annualized_volatility']*100:.2f}%")
        c3.metric("Rolling 20-observation", "—" if summary["rolling_20_latest"] is None else f"{summary['rolling_20_latest']*100:.2f}%")
        c4.metric("Observations", f"{summary['observations']:,}")
        rets = risk_metrics.return_series(history["rate"])
        vol_frame = pd.DataFrame({"date": history["date"].iloc[1:].values, "return": rets.values})
        for window in (20, 60, 90): vol_frame[f"rolling_{window}"] = vol_frame["return"].rolling(window).std() * 100
        fig = px.line(vol_frame, x="date", y=[c for c in vol_frame.columns if c.startswith("rolling_")], title="Rolling daily-return volatility")
        st.plotly_chart(_style(fig), width="stretch")
        confidence = st.select_slider("Historical VaR confidence level", options=[0.90, 0.95, 0.99], value=0.95)
        exposure = st.number_input("Exposure in INR for one-day historical loss estimate", min_value=0.0, value=1_000_000.0, step=100_000.0)
        try:
            result = risk_metrics.historical_var_cvar(rets, exposure, confidence)
            c1, c2 = st.columns(2)
            c1.metric(f"Historical VaR · {confidence:.0%}", _money(max(0, result["var_inr"])))
            c2.metric(f"Historical CVaR · {confidence:.0%}", _money(max(0, result["cvar_inr"])))
            st.caption(f"Uses {result['observations']} daily percentage returns and the worst {result['tail_observations']} tail observations. Loss = negative return × exposure. Historical VaR is a quantile, not a maximum possible loss.")
        except ValueError as exc: st.warning(str(exc))
        st.download_button("Download rate and return analysis CSV", history.assign(return_pct=history["rate"].pct_change() * 100).to_csv(index=False).encode(), file_name=f"{currency.lower()}_risk_analysis.csv", mime="text/csv")
    else:
        st.warning(meta.get("reason", "No rate history is available; VaR and volatility cannot be calculated."))
    st.subheader("Multi-currency stress test")
    exposure = exposure_manager.exposure_by_currency(ctx["enriched"])
    if exposure.empty:
        st.info("Add transactions to stress-test business cash requirements.")
    else:
        shock_cols = st.columns(min(4, len(exposure)))
        shocks = {}
        for i, cur in enumerate(exposure["currency"]): shocks[cur] = shock_cols[i % len(shock_cols)].number_input(f"{cur}/INR shock %", min_value=-50.0, max_value=50.0, value=(ctx["settings"].get("stress_pct", 5.0) if float(exposure.loc[exposure.currency == cur, "net_payable_inr"].iloc[0]) >= 0 else -ctx["settings"].get("stress_pct", 5.0)), step=0.5, key=f"shock_{cur}")
        stressed = risk_metrics.stress_portfolio(exposure, shocks)
        st.dataframe(stressed, hide_index=True, width="stretch", column_config={"net_payable_inr": st.column_config.NumberColumn("Net payable · INR", format="₹%.0f"), "cash_requirement_change_inr": st.column_config.NumberColumn("Cash requirement change · INR", format="₹%.0f")})
        st.metric("Combined change in estimated cash requirement", _money(stressed["cash_requirement_change_inr"].sum()))
    st.subheader("Early-warning alerts")
    thresholds = ctx["settings"].get("thresholds", {})
    movements, vol = {}, {}
    for cur in currencies:
        h, _ = _market_frame(ctx, cur, "1 month")
        if len(h) >= 2:
            movements[cur] = float(h.iloc[-1]["rate"] / h.iloc[-2]["rate"] - 1) * 100
            summary = risk_metrics.volatility_summary(h["rate"])
            if summary["rolling_20_latest"] is not None: vol[cur] = summary["rolling_20_latest"] * 100
    alerts = risk_metrics.build_alerts(ctx["enriched"], movements, vol, thresholds, pd.Timestamp.now(tz="UTC").isoformat(timespec="minutes"))
    if alerts.empty: st.success("No configured threshold was breached by the available observations.")
    else: st.dataframe(alerts, hide_index=True, width="stretch")
    st.download_button("Download risk alerts CSV", alerts.to_csv(index=False).encode(), file_name="risk_alerts.csv", mime="text/csv")


def cash_flow_page(ctx):
    st.title("Cash-flow forecast")
    st.caption("Estimate based on open transactions and selected rates. Dates and amounts are not guaranteed future cash flows.")
    today = date.today()
    period = st.radio("Forecast horizon", ["7 days", "30 days", "60 days", "90 days", "Custom"], horizontal=True)
    start = st.date_input("From", value=today, key="cash_start")
    end_default = today + timedelta(days=int(period.split()[0])) if period != "Custom" else today + timedelta(days=90)
    end = st.date_input("Through", value=end_default, key="cash_end")
    frame = ctx["transactions"]
    currencies = sorted(frame["currency"].dropna().unique().tolist()) if not frame.empty else []
    selected_currencies = st.multiselect("Currencies", currencies, default=currencies)
    types = st.multiselect("Transaction type", ["payable", "receivable"], default=["payable", "receivable"])
    stress = st.number_input("Adverse movement assumption (%)", min_value=0.0, max_value=100.0, value=float(ctx["settings"].get("stress_pct", 5.0)), step=0.5)
    forecast = cash_flow.forecast(frame, ctx["rates"], start, end, selected_currencies or [], types, stress)
    if forecast.empty:
        st.info("No open cash flows with available rates fall within this period.")
        return
    pay = forecast[forecast["transaction_type"] == "payable"]
    rec = forecast[forecast["transaction_type"] == "receivable"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Expected payable cash", _money(pay["estimated_inr"].sum()))
    c2.metric("Expected receipts", _money(abs(rec["estimated_inr"].sum())))
    c3.metric("Payable amount under adverse scenario", _money(pay["adverse_inr"].sum()))
    st.dataframe(forecast, hide_index=True, width="stretch", column_config={"estimated_inr": st.column_config.NumberColumn("Estimated INR · receipt negative", format="₹%.0f"), "budget_inr": st.column_config.NumberColumn("Budget INR · receipt negative", format="₹%.0f"), "adverse_inr": st.column_config.NumberColumn("Adverse INR · receipt negative", format="₹%.0f")})
    fig = px.bar(forecast, x="due_date", y="estimated_inr", color="transaction_type", facet_col="currency", title="Estimated dated cash flows (+ payable / − receivable)", color_discrete_sequence=[NAVY, TEAL])
    st.plotly_chart(_style(fig, 370), width="stretch")
    offsets = exposure_manager.potential_offsets(ctx["enriched"], int(ctx["settings"].get("maturity_bucket_days", 30)))
    st.subheader("Potential natural offsets by maturity bucket")
    st.caption("Offsets are analytical opportunities only. Settlement dates, counterparties and business constraints may prevent netting.")
    st.dataframe(offsets, hide_index=True, width="stretch")
    st.download_button("Download cash-flow forecast CSV", forecast.to_csv(index=False).encode(), file_name="cash_flow_forecast.csv", mime="text/csv")


def analyst_page(ctx):
    st.title("AI Treasury Analyst")
    st.caption("This academic build uses a deterministic report template. It does not call an LLM or generate unsupported market explanations.")
    if st.button("Generate management report", type="primary"):
        notes = []
        if not ctx["quote_meta"]: notes.append("No market quote was retrieved during this app run.")
        for currency, meta in ctx["quote_meta"].items():
            if meta.get("status") != "retrieved": notes.append(f"{currency}: provider data unavailable; manual override or budget-rate proxy may be in use.")
            elif currency in ctx["settings"].get("manual_rates", {}): notes.append(f"{currency}: a user-entered manual rate overrides the retrieved reference rate in exposure calculations.")
        report = management_report(ctx["enriched"], exposure_manager.exposure_by_currency(ctx["enriched"]), ctx["alerts"], notes, ctx["settings"].get("business_name", "Business"))
        st.session_state["management_report"] = report
    report = st.session_state.get("management_report")
    if report:
        st.markdown(report)
        st.download_button("Download report Markdown", report.encode(), file_name="fx_management_report.md", mime="text/markdown")
    else:
        st.info("Generate a report to summarize verified calculations, assumptions and data limitations.")
    st.info("A future LLM integration would need an explicit API secret and controls that constrain interpretation to verified values. The app remains fully functional without one.")


def methodology_page(ctx):
    st.title("Data and methodology")
    st.markdown("""
### Data sources and conventions
- Historical FX reference data is requested from Yahoo Finance through `yfinance`, using daily closing observations and configured ticker mappings. Availability, ticker conventions and timestamps are checked at retrieval; provider outages produce an unavailable state.
- The application expresses INR currency pairs as INR per one unit of foreign currency. INR value is amount × rate. USD/INR uses Yahoo's `INR=X` symbol; other mappings are attempted where the provider exposes them.
- A manual rate entered by the user takes precedence and is visibly labeled. When neither manual nor market data exists, the exposure dashboard uses the transaction's budget rate only as an explicitly labeled proxy for summary totals. Missing historical observations are not filled in for returns or volatility.
- Market quotes are reference observations, not executable bank prices. Historical close and retrieval timestamps remain separate.

### Statistical methods
- Simple percentage return: `r(t) = S(t) / S(t−1) − 1`.
- Daily volatility: sample standard deviation (`ddof=1`) of daily returns. Annualized volatility multiplies daily volatility by `sqrt(252)` trading days; this convention is not applied to intraday data.
- Rolling volatility uses standard deviation over 20, 60 and 90 daily observations when available.
- Historical VaR is the requested empirical quantile of one-day losses (`−return × exposure`). CVaR is the average loss at or beyond that quantile. At least 20 returns are required. VaR is not a maximum-loss bound.
- Stress-test cash requirement change is net INR payable exposure × user-entered percentage shock. Receivable shocks naturally reduce INR cash requirements when rates fall.

### Business calculations and limitations
- Payable budget variance is scenario INR cost minus budgeted INR cost. Receivable adverse variance reverses the sign, so positive always means worse for the business.
- Hedge estimate: `A × [h × F + (1 − h) × S] + costs`, for the assumed locked portion and remaining settlement spot. The tool does not source forward prices.
- The backtest uses the preceding daily close as an assumed-forward proxy and is not based on historical forward quotes. It avoids using a later observation to set the earlier proxy, but omits basis, carry, credit, execution, and contract effects.
- Natural offsets are grouped by currency and maturity bucket as potential opportunities; legal and operational netting is not assumed.
- Transaction storage is local SQLite by default and is ephemeral if hosted on Streamlit Community Cloud unless an external persistent store is configured. Do not upload confidential business records to a public deployment.
- Reproducibility metadata: application version is recorded in `pyproject.toml`; generated CSVs preserve source observations and derived fields separately where possible.
""")
    currencies = sorted(set(ctx["transactions"]["currency"].astype(str))) if not ctx["transactions"].empty else ["USD"]
    currency = st.selectbox("Inspect underlying market observations", currencies, key="method_currency")
    history, meta = _market_frame(ctx, currency, ctx["settings"].get("lookback", "1 year"))
    if history.empty: st.warning(meta.get("reason", "No history available."))
    else:
        st.caption(f"Ticker: {meta.get('ticker')} · retrieved: {meta.get('retrieved_at')} · last observation: {meta.get('observation_at')}")
        st.dataframe(history.assign(return_pct=history["rate"].pct_change() * 100), hide_index=True, width="stretch")
        st.download_button("Download underlying data plus returns CSV", history.assign(return_pct=history["rate"].pct_change() * 100).to_csv(index=False).encode(), file_name=f"{currency.lower()}_methodology_data.csv", mime="text/csv")


def settings_page(ctx):
    st.title("Settings and exports")
    st.caption("Thresholds affect alerts and risk labels. They do not predict the direction of a currency movement.")
    settings = dict(ctx["settings"])
    with st.form("settings_form"):
        business_name = st.text_input("Business or reporting label", settings.get("business_name", "Business"))
        watchlist = st.multiselect("Currency watchlist", SUPPORTED_CURRENCIES, default=settings.get("watchlist", ["USD", "EUR", "GBP", "JPY"]))
        lookback = st.selectbox("Default historical lookback", list(market_data.PERIODS), index=list(market_data.PERIODS).index(settings.get("lookback", "1 year")))
        stress_pct = st.number_input("Default adverse stress movement (%)", min_value=0.0, max_value=100.0, value=float(settings.get("stress_pct", 5.0)))
        default_hedge_pct = st.slider("Default hedge coverage (%)", 0, 100, int(settings.get("default_hedge_pct", 50)))
        precision = st.slider("Displayed FX rate decimal places", 2, 6, int(settings.get("precision", 4)))
        bucket_days = st.selectbox("Maturity bucket size", [7, 14, 30, 60, 90], index=[7, 14, 30, 60, 90].index(int(settings.get("maturity_bucket_days", 30))))
        thresholds = settings.get("thresholds", {})
        c1, c2, c3 = st.columns(3)
        movement_threshold = c1.number_input("Movement alert threshold (%)", min_value=0.0, value=float(thresholds.get("movement_pct", 5.0)))
        volatility_threshold = c2.number_input("Rolling volatility threshold (%)", min_value=0.0, value=float(thresholds.get("volatility_pct", 2.0)))
        exposure_limit = c3.number_input("Exposure alert limit (INR)", min_value=0.0, value=float(thresholds.get("exposure_limit_inr", 1_000_000.0)))
        c1, c2 = st.columns(2)
        overrun = c1.number_input("Potential cost overrun threshold (INR)", min_value=0.0, value=float(thresholds.get("overrun_inr", 250_000.0)))
        near_due = c2.number_input("Payment due soon window (days)", min_value=0, max_value=365, value=int(thresholds.get("near_due_days", 14)))
        save = st.form_submit_button("Save settings", type="primary")
    if save:
        settings.update({"business_name": business_name, "watchlist": watchlist, "lookback": lookback, "stress_pct": stress_pct, "default_hedge_pct": default_hedge_pct, "precision": precision, "maturity_bucket_days": bucket_days, "thresholds": {"movement_pct": movement_threshold, "volatility_pct": volatility_threshold, "exposure_limit_inr": exposure_limit, "overrun_inr": overrun, "near_due_days": near_due}})
        set_setting("app_settings", settings)
        st.session_state["settings"] = settings
        st.success("Settings saved.")
        st.rerun()

    st.subheader("Manual rates")
    manual_rates = settings.get("manual_rates", {})
    if manual_rates: st.dataframe(pd.DataFrame([{"currency": c, "manual_inr_per_unit": r} for c, r in manual_rates.items()]), hide_index=True, width="stretch")
    else: st.caption("No manual rates configured.")
    st.subheader("Exports")
    st.download_button("Transaction register CSV", export_transactions(), file_name="fx_transactions.csv", mime="text/csv")
    if not ctx["alerts"].empty:
        st.download_button("Current risk alerts CSV", ctx["alerts"].to_csv(index=False).encode(), file_name="risk_alerts.csv", mime="text/csv")
    if not ctx["enriched"].empty:
        st.download_button("Current exposure analysis CSV", ctx["enriched"].to_csv(index=False).encode(), file_name="exposure_analysis.csv", mime="text/csv")
    with st.expander("Local database and deployment note"):
        st.write("The default database lives in data/fx_navigator.sqlite3 and is ignored by Git. Set FXN_DB_PATH to choose a different local path. Streamlit Community Cloud local storage is not durable or shared across restarts; CSV import and export are provided for the academic prototype.")

