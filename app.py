import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Master Strategy Blueprint v3.0", layout="wide")
st.title("🛡️ Master Strategy Blueprint v3.0 — Automated Engine")

# ==============================================================================
# 1. PORTFOLIO & WALLET STATE INITIALIZATION (₹30,00,000 BASELINE)
# ==============================================================================
if "balance" not in st.session_state:
    st.session_state.balance = 3000000.0  # ₹30,00,000 Total Capital Base

if "engine1_core" not in st.session_state:
    # 50% = ₹15,00,000 across 6 ETFs (Tranche size: ₹1,50,000/mo = ₹25,000/ETF)
    st.session_state.engine1_core = {
        "MID150BEES.NS": {"units": 0, "avg_cost": 0.0},
        "JUNIORBEES.NS": {"units": 0, "avg_cost": 0.0},
        "MON100.NS": {"units": 0, "avg_cost": 0.0},
        "ICICIB22.NS": {"units": 0, "avg_cost": 0.0},
        "MODEFENCE.NS": {"units": 0, "avg_cost": 0.0},
        "PHARMABEES.NS": {"units": 0, "avg_cost": 0.0}
    }

if "engine2_swing" not in st.session_state:
    # 40% = ₹12,00,000 across 5 Themes × 4 Tiers (₹60,000/tranche)
    st.session_state.engine2_swing = {}

if "engine3_reserve" not in st.session_state:
    # 10% = ₹3,00,000 in LIQUIDBEES (Hard Floor ₹2,00,000)
    st.session_state.engine3_reserve = 300000.0

if "trade_log" not in st.session_state:
    st.session_state.trade_log = []

# ==============================================================================
# 2. BLUEPRINT MATRIX & GUARDRAIL CONFIGURATION
# ==============================================================================
SWING_MATRIX = {
    "Silver": ["KOTAKSILVE.NS", "HDFCSILVER.NS", "ICICISILVE.NS", "SILVERBEES.NS"],
    "Gold": ["GOLDBEES.NS", "HDFCGOLD.NS", "KOTAKGOLD.NS", "SETFGOLD.NS"],
    "Banking": ["BANKBEES.NS", "SETFNIFBK.NS", "KOTAKBKETF.NS", "HDFCBANKETF.NS"],
    "IT": ["ITBEES.NS", "ICICITECH.NS", "SETFIT.NS", "AXISTEC.NS"],
    "Auto": ["AUTOBEES.NS", "AUTOIETF.NS", "AUTOBEES.NS", "AUTOIETF.NS"]
}

TRAILING_STOPS = {
    "Silver": 0.09,    # 9% Trailing Stop
    "Gold": 0.07,      # 7% Trailing Stop
    "Banking": 0.07,   # 7% Trailing Stop
    "IT": 0.07,        # 7% Trailing Stop
    "Auto": 0.07       # 7% Trailing Stop
}

RESERVE_FLOOR = 200000.0  # ₹2.00 Lakhs Hard Reserve Floor

# ==============================================================================
# 3. SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.header("🕹️ Strategy Controls")

all_symbols = list(st.session_state.engine1_core.keys()) + [t for theme in SWING_MATRIX.values() for t in theme]
selected_symbol = st.sidebar.selectbox("Analyze Instrument", all_symbols, index=0)

auto_mode = st.sidebar.checkbox("Enable 3:15 PM Automated Guardrails", value=True)

if st.sidebar.button("Reset Portfolio to Baseline (₹30L)"):
    st.session_state.balance = 3000000.0
    st.session_state.engine1_core = {k: {"units": 0, "avg_cost": 0.0} for k in st.session_state.engine1_core}
    st.session_state.engine2_swing = {}
    st.session_state.engine3_reserve = 300000.0
    st.session_state.trade_log = []
    st.sidebar.success("Reset portfolio to ₹30,00,000 baseline!")

# ==============================================================================
# 4. MAIN ENGINE EXECUTION & TECHNICAL ANALYSIS
# ==============================================================================
try:
    ticker = yf.Ticker(selected_symbol)
    df = ticker.history(period="1y", interval="1d")
    df = df.dropna(subset=['Close'])  # Clean out unclosed/empty NaN rows

    if not df.empty and len(df) >= 200:
        # Technical Indicator Calculations
        df['20_EMA'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['200_EMA'] = df['Close'].ewm(span=200, adjust=False).mean()

        latest_price = float(df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2])
        ema_20 = float(df['20_EMA'].iloc[-1])
        ema_200 = float(df['200_EMA'].iloc[-1])

        # Guardrail Conditions
        regime_shield = (latest_price > ema_20) and (latest_price > ema_200)  # Rule 1
        wedge_filter = (latest_price > ema_200) and (latest_price > prev_price) # Rule 2 Green confirmation above 200-EMA

        # Top Display Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Available Liquidity", f"₹{st.session_state.balance:,.2f}")
        c2.metric("Reserve Pool (LIQUIDBEES)", f"₹{st.session_state.engine3_reserve:,.2f}")
        c3.metric(f"Quote ({selected_symbol})", f"₹{latest_price:,.2f}")
        c4.metric("200-EMA Regime Shield", "PASSED ✅" if regime_shield else "BLOCKED ❌")

        # Interactive Chart View
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'))
        fig.add_trace(go.Scatter(x=df.index, y=df['20_EMA'], line=dict(color='green', width=1.5), name='20 EMA'))
        fig.add_trace(go.Scatter(x=df.index, y=df['200_EMA'], line=dict(color='red', width=2), name='200 EMA Shield'))
        fig.update_layout(title=f"{selected_symbol} Technical Guardrails Analysis", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # Tabbed Allocations & Performance Logs
        tab1, tab2, tab3, tab4 = st.tabs([
            "Engine 1: Core Wealth (50%)", 
            "Engine 2: Tactical Swing (40%)", 
            "Engine 3: Opportunity Reserve (10%)",
            "Execution Audit Log"
        ])

        with tab1:
            st.subheader("Engine 1: Core Wealth Basket (₹15,00,000 Rollout)")
            core_df = pd.DataFrame([
                {"ETF": k, "Units": v["units"], "Avg Cost": round(v["avg_cost"], 2)} 
                for k, v in st.session_state.engine1_core.items()
            ])
            st.dataframe(core_df, use_container_width=True)

            if st.button("Execute Monthly Core Tranche (₹1.5 Lakhs)"):
                tranche_per_etf = 25000.0
                for etf in st.session_state.engine1_core:
                    e_price = float(yf.Ticker(etf).history(period="1d", interval="1m")['Close'].iloc[-1])
                    qty = int(tranche_per_etf // e_price)
                    if qty > 0 and st.session_state.balance >= (qty * e_price):
                        st.session_state.balance -= (qty * e_price)
                        prev_u = st.session_state.engine1_core[etf]["units"]
                        prev_cost = st.session_state.engine1_core[etf]["avg_cost"]
                        new_u = prev_u + qty
                        new_cost = ((prev_u * prev_cost) + (qty * e_price)) / new_u if new_u > 0 else e_price
                        
                        st.session_state.engine1_core[etf] = {"units": new_u, "avg_cost": new_cost}
                        st.session_state.trade_log.append({
                            "Timestamp": pd.Timestamp.now(), "Engine": "Core", "ETF": etf, "Action": "BUY", "Qty": qty, "Price": e_price
                        })
                st.success("Deployed monthly tranche across Core ETFs!")

        with tab2:
            st.subheader("Engine 2: Tactical Swing 5x4 Matrix (₹12,00,000 Allocation)")
            swing_df = pd.DataFrame([
                {"ETF": k, "Units": v.get("units", 0), "Avg Cost": round(v.get("avg_cost", 0.0), 2)} 
                for k, v in st.session_state.engine2_swing.items()
            ])
            st.dataframe(swing_df if not swing_df.empty else pd.DataFrame(columns=["ETF", "Units", "Avg Cost"]), use_container_width=True)

        with tab3:
            st.subheader("Engine 3: Opportunity Reserve (Hard Floor ₹2.00 Lakhs)")
            st.metric("LIQUIDBEES Reserve Balance", f"₹{st.session_state.engine3_reserve:,.2f}")
            st.caption("Protects against systemic drawdowns while funding momentum siphoning (+25% winners).")

        with tab4:
            st.subheader("Audit Log & Order History")
            st.dataframe(pd.DataFrame(st.session_state.trade_log), use_container_width=True)

    else:
        st.warning("Fetching initial market quotes. Refresh page if charts take a moment to load.")

except Exception as e:
    st.error(f"Error executing engine analysis: {e}")
