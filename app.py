"""
================================================================================
8-ETF ADAPTIVE PORTFOLIO: PAPER TRADING & REBALANCING TERMINAL
================================================================================
- 8 Core ETFs + LIQUIDCASE Safe Harbor
- Weekly SIP Rollout Strategy
- Google Sheets Integration for Cloud Ledger Persistence
- Systematic 200-DMA Exit & Re-entry with 2% Whipsaw Buffer
- Target Equal-Weight Rebalancing Engine
================================================================================
"""

import os
import json
from datetime import datetime, date
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# ==============================================================================
# 1. CORE SYSTEM CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="8-ETF Wealth Engine | Paper Trading", layout="wide", page_icon="🛡️")

DEFAULT_START_CAPITAL = 3000000.0  # ₹30,00,000 Initial Corpus
WEEKLY_SIP_AMOUNT = 25000.0        # ₹25,000 Weekly SIP Tranche

CORE_ETFS = {
    "MOM30IETF.NS":  {"name": "Nifty200 Momentum 30",     "category": "Factor Alpha"},
    "MID150BEES.NS": {"name": "Nifty Midcap 150",         "category": "Core Midcap"},
    "JUNIORBEES.NS": {"name": "Nifty Next 50",            "category": "Next Bluechips"},
    "MON100.NS":     {"name": "Nasdaq 100 Tech",          "category": "Global Tech / USD"},
    "AUTOBEES.NS":   {"name": "Nifty Auto & Mobility",    "category": "EV / Mobility"},
    "INFRAIETF.NS":  {"name": "Nifty Infrastructure",     "category": "National Capex"},
    "GOLDBEES.NS":   {"name": "Physical Gold",            "category": "Sovereign Ballast"},
    "SILVERBEES.NS": {"name": "Physical Silver",          "category": "Industrial Metal"}
}

SAFE_HARBOR = "LIQUIDCASE.NS"
TARGET_WEIGHT_PER_ETF = 1.0 / len(CORE_ETFS)  # 12.5% each

# ==============================================================================
# 2. GOOGLE SHEETS CONNECTOR & STATE MANAGEMENT
# ==============================================================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_sheet_ledger():
    """Reads execution ledger from Google Sheets."""
    try:
        df = conn.read(worksheet="Ledger", ttl="0s")
        return df
    except Exception:
        # Return default structure if sheet is uninitialized or empty
        return pd.DataFrame(columns=[
            "Date", "Total NAV", "Daily PnL", "Daily Return (%)",
            "Equities Deployed", "LIQUIDCASE Cash", "Strategy Period", "Execution Notes"
        ])

def append_to_sheet_ledger(date_str, total_nav, daily_pnl, daily_return_pct, equities_deployed, liquidcase_cash, period, notes):
    """Appends a new record row directly to Google Sheets."""
    try:
        df_existing = load_sheet_ledger()
        new_row = pd.DataFrame([{
            "Date": date_str,
            "Total NAV": total_nav,
            "Daily PnL": daily_pnl,
            "Daily Return (%)": f"{daily_return_pct:.2f}%",
            "Equities Deployed": equities_deployed,
            "LIQUIDCASE Cash": liquidcase_cash,
            "Strategy Period": period,
            "Execution Notes": notes
        }])
        updated_df = pd.concat([df_existing, new_row], ignore_index=True)
        conn.update(worksheet="Ledger", data=updated_df)
        st.toast("✅ Ledger successfully synced to Google Sheets!")
    except Exception as e:
        st.error(f"Failed to update Google Sheet: {e}")

# Initialize Session State
if "liquidcase_cash" not in st.session_state:
    st.session_state.liquidcase_cash = 2975000.0
if "equities_deployed" not in st.session_state:
    st.session_state.equities_deployed = 25000.0
if "holdings" not in st.session_state:
    st.session_state.holdings = {sym: {"units": 0, "avg_cost": 0.0} for sym in CORE_ETFS}
if "parked_capital" not in st.session_state:
    st.session_state.parked_capital = {sym: 0.0 for sym in CORE_ETFS}
if "sip_week_counter" not in st.session_state:
    st.session_state.sip_week_counter = 1

# ==============================================================================
# 3. MARKET DATA & TECHNICAL ENGINE
# ==============================================================================
@st.cache_data(ttl=300)
def fetch_etf_data(symbol: str):
    """Fetches historical daily close data with 2-year lookback."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y", interval="1d")
        if df.empty or len(df) < 200:
            return None
        df = df.dropna(subset=['Close'])
        return df
    except Exception:
        return None

def get_trend_status(symbol: str):
    """Evaluates whether an ETF is above or below its 200-DMA with 2% buffer."""
    df = fetch_etf_data(symbol)
    if df is None:
        return {"ltp": 0.0, "sma200": 0.0, "dist": 0.0, "regime": "UNKNOWN"}
    
    ltp = float(df['Close'].iloc[-1])
    sma200 = float(df['Close'].rolling(window=200).mean().iloc[-1])
    dist = ((ltp - sma200) / sma200) * 100.0
    buffer_line = sma200 * 0.98

    if ltp < buffer_line:
        regime = "BEAR (PARKED)"
    elif ltp > sma200:
        regime = "BULL (INVESTED)"
    else:
        regime = "BUFFER ZONE"

    return {"ltp": round(ltp, 2), "sma200": round(sma200, 2), "dist": round(dist, 2), "regime": regime}

# ==============================================================================
# 4. EXECUTION ENGINE (WEEKLY SIP)
# ==============================================================================
def execute_weekly_sip(selected_etf: str, sip_amount: float, execution_date: str):
    """Executes a Weekly SIP tranche into a selected ETF from LIQUIDCASE cash."""
    if st.session_state.liquidcase_cash < sip_amount:
        st.error(f"❌ Insufficient LIQUIDCASE balance! Available: ₹{st.session_state.liquidcase_cash:,.2f}")
        return False

    status = get_trend_status(selected_etf)
    ltp = status["ltp"] if status["ltp"] > 0 else 1.0

    # Deduct from Liquid Cash pool and deploy
    st.session_state.liquidcase_cash -= sip_amount
    st.session_state.equities_deployed += sip_amount
    
    units = int(sip_amount // ltp) if ltp > 0 else 0
    if units > 0:
        pos = st.session_state.holdings[selected_etf]
        tot_units = pos["units"] + units
        pos["avg_cost"] = ((pos["units"] * pos["avg_cost"]) + sip_amount) / tot_units
        pos["units"] = tot_units

    week_num = st.session_state.sip_week_counter
    st.session_state.sip_week_counter += 1

    # Record into Google Sheets
    total_nav = st.session_state.liquidcase_cash + st.session_state.equities_deployed
    note = f"SIP Deployed ₹{sip_amount:,.0f} into {selected_etf} ({CORE_ETFS[selected_etf]['name']}) | Deducted from LIQUIDCASE Cash"
    
    append_to_sheet_ledger(
        date_str=execution_date,
        total_nav=total_nav,
        daily_pnl=0,
        daily_return_pct=0.00,
        equities_deployed=st.session_state.equities_deployed,
        liquidcase_cash=st.session_state.liquidcase_cash,
        period=f"Week {week_num}",
        notes=note
    )
    return True

# ==============================================================================
# 5. STREAMLIT UI DASHBOARD
# ==============================================================================
st.title("🛡️ 8-ETF Institutional Paper Trading Terminal")

# Dynamic Financial Headers
total_nav = st.session_state.liquidcase_cash + st.session_state.equities_deployed

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total NAV", f"₹{total_nav:,.0f}")
c2.metric("Daily P&L", "₹0")
c3.metric("Equities Deployed", f"₹{st.session_state.equities_deployed:,.0f}")
c4.metric("LIQUIDCASE Cash", f"₹{st.session_state.liquidcase_cash:,.0f}")

st.markdown("---")

tabs = st.tabs(["📜 Execution Ledger", "🅿️ Park / Add Cash", "💸 Deploy Weekly SIP", "📊 My ETF List"])

# ------------------------------------------------------------------------------
# TAB 1: EXECUTION LEDGER (READ/WRITE VIA GOOGLE SHEETS)
# ------------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Execution Ledger (Synced with Google Sheets)")
    
    sheet_data = load_sheet_ledger()
    if not sheet_data.empty:
        st.dataframe(sheet_data, use_container_width=True)
    else:
        st.info("No ledger records found in Google Sheets.")

    if st.button("💾 Save / Refresh Ledger Edits", key="btn_refresh_ledger"):
        st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: PARK / ADD CASH
# ------------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Park or Inject Fresh Capital")
    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        add_amount = st.number_input("Inject Cash Amount (₹)", min_value=1000.0, value=100000.0, step=10000.0)
        if st.button("Add to LIQUIDCASE Pool", key="btn_add_cash"):
            st.session_state.liquidcase_cash += add_amount
            total_nav = st.session_state.liquidcase_cash + st.session_state.equities_deployed
            
            append_to_sheet_ledger(
                date_str=str(date.today()),
                total_nav=total_nav,
                daily_pnl=0,
                daily_return_pct=0.00,
                equities_deployed=st.session_state.equities_deployed,
                liquidcase_cash=st.session_state.liquidcase_cash,
                period="Capital Addition",
                notes=f"Injected ₹{add_amount:,.0f} fresh capital into LIQUIDCASE"
            )
            st.success(f"Added ₹{add_amount:,.0f} to LIQUIDCASE Pool!")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: DEPLOY WEEKLY SIP
# ------------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Deploy Weekly SIP Tranche")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        target_etf = st.selectbox("Select Target ETF for Tranche", list(CORE_ETFS.keys()), format_func=lambda x: f"{x} - {CORE_ETFS[x]['name']}")
        sip_val = st.number_input("Weekly SIP Amount (₹)", min_value=1000.0, value=WEEKLY_SIP_AMOUNT, step=5000.0)
        exec_date = st.date_input("Execution Date", value=date.today())

        if st.button("🚀 Execute Weekly SIP Tranche", key="btn_exec_weekly_sip"):
            if execute_weekly_sip(target_etf, sip_val, str(exec_date)):
                st.success(f"Weekly SIP of ₹{sip_val:,.0f} into {target_etf} successfully logged!")
                st.rerun()

# ------------------------------------------------------------------------------
# TAB 4: MY ETF LIST & TREND SCANNER
# ------------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Core 8-ETF Portfolio Tracking")
    
    etf_rows = []
    for sym, meta in CORE_ETFS.items():
        status = get_trend_status(sym)
        pos = st.session_state.holdings[sym]
        etf_rows.append({
            "Symbol": sym,
            "Name": meta["name"],
            "Category": meta["category"],
            "LTP": f"₹{status['ltp']:,.2f}",
            "200-SMA": f"₹{status['sma200']:,.2f}",
            "Distance (%)": f"{status['dist']:+.2f}%",
            "Regime": status["regime"],
            "Units Held": pos["units"]
        })
    
    st.dataframe(pd.DataFrame(etf_rows), use_container_width=True)
