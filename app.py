"""
================================================================================
8-ETF ADAPTIVE PORTFOLIO: PAPER TRADING & REBALANCING TERMINAL
================================================================================
- 8 Core ETFs + LIQUIDBEES Safe Harbor
- Monthly SIP Rollout (Default: 15th of every month @ ₹3,00,000/month)
- Systematic 200-DMA Exit & Re-entry with 2% Whipsaw Buffer
- Target 12.5% Equal-Weight Rebalancing Engine
================================================================================
"""

import os
import json
from datetime import datetime, date
import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

# ==============================================================================
# 1. CORE SYSTEM CONFIGURATION
# ==============================================================================
st.set_page_config(page_title="8-ETF Wealth Engine | Paper Trading", layout="wide", page_icon="🛡️")

DATA_FILE = "portfolio_state.json"
DEFAULT_START_CAPITAL = 3000000.0  # ₹30,00,000 Initial Corpus
MONTHLY_SIP_AMOUNT = 300000.0     # ₹3,00,000 per month (10 months)
SIP_EXECUTION_DAY = 15            # 15th of the month

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

SAFE_HARBOR = "LIQUIDBEES.NS"
TARGET_WEIGHT_PER_ETF = 1.0 / len(CORE_ETFS)  # 12.5% each

# ==============================================================================
# 2. STATE PERSISTENCE & DATA MANAGEMENT
# ==============================================================================
def load_state():
    """Loads saved paper trading portfolio from disk."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_state():
    """Serializes the current session state to disk."""
    state = {
        "cash_balance": st.session_state.cash_balance,
        "holdings": st.session_state.holdings,
        "parked_capital": st.session_state.parked_capital,
        "trade_log": st.session_state.trade_log,
        "sip_log": st.session_state.sip_log,
        "total_infused": st.session_state.total_infused
    }
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=4, default=str)

# Initialize Session State
saved = load_state()
if "cash_balance" not in st.session_state:
    if saved:
        st.session_state.cash_balance = saved.get("cash_balance", DEFAULT_START_CAPITAL)
        st.session_state.holdings = saved.get("holdings", {sym: {"units": 0, "avg_cost": 0.0} for sym in CORE_ETFS})
        st.session_state.parked_capital = saved.get("parked_capital", {sym: 0.0 for sym in CORE_ETFS})
        st.session_state.trade_log = saved.get("trade_log", [])
        st.session_state.sip_log = saved.get("sip_log", [])
        st.session_state.total_infused = saved.get("total_infused", DEFAULT_START_CAPITAL)
    else:
        st.session_state.cash_balance = DEFAULT_START_CAPITAL
        st.session_state.holdings = {sym: {"units": 0, "avg_cost": 0.0} for sym in CORE_ETFS}
        st.session_state.parked_capital = {sym: 0.0 for sym in CORE_ETFS}
        st.session_state.trade_log = []
        st.session_state.sip_log = []
        st.session_state.total_infused = DEFAULT_START_CAPITAL
        save_state()

# ==============================================================================
# 3. MARKET DATA & 200-DMA TECHNICAL ENGINE
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
# 4. PAPER EXECUTION ENGINE
# ==============================================================================
def record_trade(action: str, symbol: str, units: int, price: float, total: float, reason: str):
    """Logs an executed paper trade."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.trade_log.insert(0, {
        "timestamp": timestamp,
        "action": action,
        "symbol": symbol,
        "units": units,
        "price": round(price, 2),
        "total": round(total, 2),
        "reason": reason
    })

def execute_sip_tranche(execution_date_str: str):
    """Deploys the monthly SIP tranche (₹3,00,000 / 8 = ₹37,500 per ETF)."""
    tranche_per_etf = MONTHLY_SIP_AMOUNT / len(CORE_ETFS)
    
    if st.session_state.cash_balance < MONTHLY_SIP_AMOUNT:
        st.error(f"❌ Insufficient cash for full SIP! Available: ₹{st.session_state.cash_balance:,.2f}")
        return False

    executed_count = 0
    for symbol in CORE_ETFS:
        status = get_trend_status(symbol)
        ltp = status["ltp"]
        if ltp <= 0:
            continue

        # RULE: If Bearish (< 200-DMA - 2%), park directly into LIQUIDBEES pool
        if status["regime"] == "BEAR (PARKED)":
            st.session_state.cash_balance -= tranche_per_etf
            st.session_state.parked_capital[symbol] += tranche_per_etf
            record_trade("PARK_CASH", symbol, 0, ltp, tranche_per_etf, "SIP 15th: Below 200-DMA (Parked in Liquid)")
            executed_count += 1
        else:
            units = int(tranche_per_etf // ltp)
            actual_cost = units * ltp
            if units > 0:
                pos = st.session_state.holdings[symbol]
                total_units = pos["units"] + units
                pos["avg_cost"] = ((pos["units"] * pos["avg_cost"]) + actual_cost) / total_units
                pos["units"] = total_units
                st.session_state.cash_balance -= actual_cost
                record_trade("BUY_SIP", symbol, units, ltp, actual_cost, "SIP 15th: Trend Above 200-DMA")
                executed_count += 1

    st.session_state.sip_log.append({
        "date": execution_date_str,
        "amount": MONTHLY_SIP_AMOUNT,
        "note": f"Completed 15th SIP across {executed_count} ETFs"
    })
    save_state()
    return True

def execute_exit_to_liquid(symbol: str, ltp: float):
    """Liquidates ETF and parks proceeds into LiquidBeES."""
    pos = st.session_state.holdings[symbol]
    qty = pos["units"]
    if qty <= 0:
        return

    proceeds = qty * ltp
    pnl = proceeds - (qty * pos["avg_cost"])
    st.session_state.parked_capital[symbol] += proceeds
    pos["units"] = 0
    pos["avg_cost"] = 0.0

    record_trade("EXIT_TO_LIQUID", symbol, qty, ltp, proceeds, f"Price < 200-SMA -2% | Realized P&L: ₹{pnl:+,.2f}")
    save_state()

def execute_reentry_from_liquid(symbol: str, ltp: float):
    """Deploys parked LiquidBeES capital back into the reclaimed ETF."""
    pool = st.session_state.parked_capital.get(symbol, 0.0)
    if pool <= 0:
        return

    units = int(pool // ltp)
    actual_cost = units * ltp
    if units > 0:
        pos = st.session_state.holdings[symbol]
        pos["units"] = units
        pos["avg_cost"] = ltp
        remainder = pool - actual_cost
        st.session_state.cash_balance += remainder
        st.session_state.parked_capital[symbol] = 0.0

        record_trade("REENTRY_BUY", symbol, units, ltp, actual_cost, "Reclaimed 200-SMA: Redeployed from Liquid")
        save_state()

# ==============================================================================
# 5. STREAMLIT UI DASHBOARD
# ==============================================================================
st.title("🛡️ 8-ETF Institutional Paper Trading Terminal")
st.caption("Engineered for 200-DMA Trend Defense, 15th Monthly SIPs, and Clean Rebalancing")

# Top Navigation Bar & Live Calculations
market_data = {sym: get_trend_status(sym) for sym in CORE_ETFS}

equity_val = sum(st.session_state.holdings[sym]["units"] * market_data[sym]["ltp"] for sym in CORE_ETFS)
parked_val = sum(st.session_state.parked_capital.values())
total_nav = st.session_state.cash_balance + equity_val + parked_val
total_pnl = total_nav - st.session_state.total_infused
total_pnl_pct = (total_pnl / st.session_state.total_infused) * 100.0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total NAV", f"₹{total_nav:,.2f}", f"{total_pnl_pct:+.2f}%")
c2.metric("Equities Deployed", f"₹{equity_val:,.2f}")
c3.metric("Parked in LIQUIDBEES", f"₹{parked_val:,.2f}")
c4.metric("Unallocated Cash", f"₹{st.session_state.cash_balance:,.2f}")
c5.metric("SIPs Completed", f"{len(st.session_state.sip_log)} / 10 Months")

st.markdown("---")

tabs = st.tabs(["📊 Market & Trend Matrix", "📅 15th Monthly SIP", "⚖️ Portfolio Rebalancing", "📜 Trade Ledger", "⚙️ Admin & Infusions"])

# ------------------------------------------------------------------------------
# TAB 1: REAL-TIME TREND MATRIX & CIRCUIT BREAKER
# ------------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Automated 200-DMA Trend-Following Scanner")
    st.info("💡 **Rule:** Price < 200-SMA by >2% triggers an EXIT to LIQUIDBEES. Price > 200-SMA triggers RE-ENTRY.")

    matrix_rows = []
    for sym, info in CORE_ETFS.items():
        data = market_data[sym]
        pos = st.session_state.holdings[sym]
        parked = st.session_state.parked_capital[sym]
        curr_val = pos["units"] * data["ltp"]
        pnl = curr_val - (pos["units"] * pos["avg_cost"]) if pos["units"] > 0 else 0.0

        matrix_rows.append({
            "Ticker": sym,
            "Name": info["name"],
            "LTP": f"₹{data['ltp']:,.2f}",
            "200-SMA": f"₹{data['sma200']:,.2f}",
            "Dist (%)": f"{data['dist']:+.2f}%",
            "Status": data["regime"],
            "Units Held": pos["units"],
            "Holding Value": f"₹{curr_val:,.2f}",
            "Parked (Liquid)": f"₹{parked:,.2f}",
            "Unrealized P&L": f"₹{pnl:+,.2f}"
        })

    st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True)

    # Automated Trigger Checks
    st.markdown("#### ⚡ Circuit Breaker Action Panel")
    act_col1, act_col2 = st.columns(2)
    
    with act_col1:
        st.markdown("**Pending Exits (Breached 200-DMA by >2%):**")
        exit_candidates = [sym for sym in CORE_ETFS if market_data[sym]["regime"] == "BEAR (PARKED)" and st.session_state.holdings[sym]["units"] > 0]
        if exit_candidates:
            for s in exit_candidates:
                st.warning(f"⚠️ {s} has broken down below 200-SMA!")
                if st.button(f"Execute Exit to Liquid for {s}", key=f"btn_exit_{s}"):
                    execute_exit_to_liquid(s, market_data[s]["ltp"])
                    st.rerun()
        else:
            st.success("All invested ETFs are holding above their 200-DMA threshold.")

    with act_col2:
        st.markdown("**Pending Re-Entries (Reclaimed 200-DMA):**")
        reentry_candidates = [sym for sym in CORE_ETFS if market_data[sym]["regime"] == "BULL (INVESTED)" and st.session_state.parked_capital[sym] > 0]
        if reentry_candidates:
            for s in reentry_candidates:
                st.info(f"🟢 {s} has reclaimed its 200-SMA! (Parked: ₹{st.session_state.parked_capital[s]:,.2f})")
                if st.button(f"Deploy Back into {s}", key=f"btn_reenter_{s}"):
                    execute_reentry_from_liquid(s, market_data[s]["ltp"])
                    st.rerun()
        else:
            st.write("No parked capital currently eligible for re-entry.")

# ------------------------------------------------------------------------------
# TAB 2: 15TH OF THE MONTH SIP ENGINE
# ------------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Monthly Rollout Manager (₹3,00,000 on the 15th)")
    st.write(f"Tranche Allocation per ETF: **₹{MONTHLY_SIP_AMOUNT / len(CORE_ETFS):,.2f}**")
    
    col_sip1, col_sip2 = st.columns([2, 1])
    with col_sip1:
        sim_date = st.date_input("Simulation Date", value=date.today())
        is_15th = sim_date.day == SIP_EXECUTION_DAY

        if is_15th:
            st.success(f"🎯 Today is the **15th** of the month! SIP execution is ready.")
        else:
            st.info(f"Selected date is the **{sim_date.day}th**. You can manually force-execute the 15th SIP below.")

        if st.button("🚀 Execute Monthly ₹3.00 Lakh SIP Tranche"):
            success = execute_sip_tranche(str(sim_date))
            if success:
                st.success(f"✅ Successfully executed monthly tranche for {sim_date}!")
                st.rerun()

    with col_sip2:
        st.markdown("#### 📜 SIP History")
        if st.session_state.sip_log:
            st.dataframe(pd.DataFrame(st.session_state.sip_log), use_container_width=True)
        else:
            st.caption("No SIP tranches executed yet.")

# ------------------------------------------------------------------------------
# TAB 3: TARGET REBALANCING (EQUAL-WEIGHT 12.5%)
# ------------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Annual / Periodic Equal-Weight Rebalancing")
    st.caption("Rebalances the portfolio back to 12.5% per ETF without human guesswork.")

    target_per_etf = total_nav * TARGET_WEIGHT_PER_ETF
    st.write(f"Target Value per Asset (12.5% of NAV): **₹{target_per_etf:,.2f}**")

    rebalance_plan = []
    for sym, info in CORE_ETFS.items():
        ltp = market_data[sym]["ltp"]
        pos = st.session_state.holdings[sym]
        parked = st.session_state.parked_capital[sym]
        current_asset_val = (pos["units"] * ltp) + parked
        diff = target_per_etf - current_asset_val
        diff_pct = ((current_asset_val - target_per_etf) / target_per_etf) * 100.0

        rebalance_plan.append({
            "ETF": sym,
            "Current Total Value": round(current_asset_val, 2),
            "Target Value": round(target_per_etf, 2),
            "Deviation (₹)": round(diff, 2),
            "Drift (%)": f"{diff_pct:+.2f}%",
            "Recommended Action": f"BUY ₹{diff:,.2f}" if diff > 5000 else (f"TRIM ₹{-diff:,.2f}" if diff < -5000 else "BALANCED")
        })

    rebalance_df = pd.DataFrame(rebalance_plan)
    st.dataframe(rebalance_df, use_container_width=True)

    if st.button("⚖️ Execute Automatic Rebalancing Alignment"):
        for row in rebalance_plan:
            sym = row["ETF"]
            diff = row["Deviation (₹)"]
            ltp = market_data[sym]["ltp"]
            if ltp <= 0:
                continue

            # If underweight, add from unallocated cash if available
            if diff > 5000 and st.session_state.cash_balance >= diff:
                units = int(diff // ltp)
                actual = units * ltp
                if units > 0:
                    pos = st.session_state.holdings[sym]
                    tot = pos["units"] + units
                    pos["avg_cost"] = ((pos["units"] * pos["avg_cost"]) + actual) / tot
                    pos["units"] = tot
                    st.session_state.cash_balance -= actual
                    record_trade("REBALANCE_BUY", sym, units, ltp, actual, "Rebalance target alignment")

            # If overweight, trim excess
            elif diff < -5000:
                trim_val = -diff
                units_to_trim = int(trim_val // ltp)
                pos = st.session_state.holdings[sym]
                if pos["units"] >= units_to_trim and units_to_trim > 0:
                    proceeds = units_to_trim * ltp
                    pos["units"] -= units_to_trim
                    st.session_state.cash_balance += proceeds
                    record_trade("REBALANCE_TRIM", sym, units_to_trim, ltp, proceeds, "Trimming overweight back to 12.5%")

        save_state()
        st.success("✅ Portfolio successfully rebalanced to target weights!")
        st.rerun()

# ------------------------------------------------------------------------------
# TAB 4: AUDIT LEDGER
# ------------------------------------------------------------------------------
with tabs[3]:
    st.subheader("📜 Complete Paper Trade Audit Log")
    if st.session_state.trade_log:
        st.dataframe(pd.DataFrame(st.session_state.trade_log), use_container_width=True)
    else:
        st.info("No paper trades recorded yet.")

# ------------------------------------------------------------------------------
# TAB 5: ADMIN & CAPITAL INFUSIONS
# ------------------------------------------------------------------------------
with tabs[4]:
    st.subheader("⚙️ Portfolio Administration")
    
    col_inf1, col_inf2 = st.columns(2)
    with col_inf1:
        st.markdown("#### 💰 Inject Capital (e.g., ₹50 Lakhs in Year 3/4)")
        infusion_amount = st.number_input("Infusion Amount (₹)", min_value=10000.0, step=100000.0, value=5000000.0)
        if st.button("Inject Fresh Capital"):
            st.session_state.cash_balance += infusion_amount
            st.session_state.total_infused += infusion_amount
            record_trade("CAPITAL_INFUSION", "CASH", 0, 1.0, infusion_amount, "Fresh milestone injection")
            save_state()
            st.success(f"✅ Successfully added ₹{infusion_amount:,.2f} to unallocated cash balance!")
            st.rerun()

    with col_inf2:
        st.markdown("#### ⚠️ Reset State")
        if st.button("🔴 Reset Portfolio to Factory ₹30L State"):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.session_state.clear()
            st.rerun()
