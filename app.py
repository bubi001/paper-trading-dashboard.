import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# ==============================================================================
# 1. PAGE SETUP & SESSION STATE INITIALIZATION (₹30,00,000 BASELINE)
# ==============================================================================
st.set_page_config(page_title="Master Strategy Blueprint v3.0", layout="wide", page_icon="🛡️")
st.title("🛡️ Master Strategy Blueprint v3.0 — Production Engine")

RESERVE_FLOOR = 200000.0  # ₹2,00,000 Hard Reserve Floor

# Working Capital: ₹27,00,000 + Reserve: ₹3,00,000 = ₹30,00,000 Total Capital Base
if "balance" not in st.session_state:
    st.session_state.balance = 2700000.0  # Funds Engine 1 (₹15L) & Engine 2 (₹12L)

if "engine1_core" not in st.session_state:
    # 50% = ₹15,00,000 across 4 Factor Pillars (Monthly Tranche: ₹1,50,000)
    st.session_state.engine1_core = {
        "MOM30IETF.NS":  {"units": 0, "avg_cost": 0.0, "target_tranche": 45000.0, "name": "Nifty200 Momentum 30"},
        "MID150BEES.NS": {"units": 0, "avg_cost": 0.0, "target_tranche": 40000.0, "name": "Nifty Midcap 150"},
        "JUNIORBEES.NS": {"units": 0, "avg_cost": 0.0, "target_tranche": 35000.0, "name": "Nifty Next 50"},
        "MON100.NS":     {"units": 0, "avg_cost": 0.0, "target_tranche": 30000.0, "name": "Nasdaq 100 Global Tech"}
    }

if "engine2_swing" not in st.session_state:
    # 40% = ₹12,00,000 across 5 Themes × 4 Tiers (₹60,000/tranche)
    st.session_state.engine2_swing = {}

if "engine3_reserve" not in st.session_state:
    # 10% = ₹3,00,000 in LIQUIDBEES (Floor: ₹2,00,000; Surplus funds Bottom Fishing)
    st.session_state.engine3_reserve = 300000.0

if "trade_log" not in st.session_state:
    st.session_state.trade_log = []

# ==============================================================================
# 2. SWING MATRIX: ASCENDING VOLUME (Lowest -> Largest)
# ==============================================================================
SWING_MATRIX = {
    # Tier 1 (~₹20-30 Cr) -> Tier 2 (~₹25-45 Cr) -> Tier 3 (~₹40-80 Cr) -> Tier 4 (>₹100 Cr)
    "Gold": [
        "ICICIGOLD.NS",
        "HDFCGOLD.NS",
        "TATAGOLD.NS",
        "GOLDBEES.NS"
    ],

    # Tier 1 (~₹30-50 Cr) -> Tier 2 (~₹40-80 Cr) -> Tier 3 (~₹60-120 Cr) -> Tier 4 (>₹150 Cr)
    "Silver": [
        "HDFCSILVER.NS",
        "SILVERIETF.NS",
        "TATSILV.NS",
        "SILVERBEES.NS"
    ],

    # Tier 1 (~₹10-15 Cr) -> Tier 2 (~₹20-45 Cr) -> Tier 3 (>₹40-80 Cr)
    "Banking": [
        "SETFNIFBK.NS",
        "PSUBNKBEES.NS",
        "BANKBEES.NS"
    ],

    # Tier 1 (~₹2 Cr/day) -> Tier 2 (~₹30 Cr/day King)
    "IT": [
        "ITIETF.NS",   # 1st: ICICI Prudential Nifty IT ETF
        "ITBEES.NS"    # 2nd: Nippon India Nifty IT ETF
    ],

    # Only Auto ETF meeting institutional scale
    "Auto": [
        "AUTOBEES.NS"
    ],

    # Rotational Tactical Theme
    "Defence/PSU": [
        "MODEFENCE.NS",
        "CPSEETF.NS"
    ]
}

TRAILING_STOPS = {
    "Gold": 0.07,
    "Silver": 0.09,
    "Banking": 0.07,
    "IT": 0.07,
    "Auto": 0.07,
    "Defence/PSU": 0.08,
    "Dip-Fishing": 0.05
}

DIP_CANDIDATES = ["NIFTYBEES.NS", "BANKBEES.NS", "ITBEES.NS", "JUNIORBEES.NS", "GOLDBEES.NS"]

# ==============================================================================
# 3. CACHED DATA & TECHNICAL INDICATOR CALCULATOR
# ==============================================================================
@st.cache_data(ttl=300)
def fetch_ticker_data(symbol: str):
    """Fetches historical daily bars with error handling."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        if df.empty or len(df) < 20:
            return None
        df = df.dropna(subset=['Close'])
        return df
    except Exception:
        return None

def calculate_indicators(df):
    """Calculates EMA20, EMA200, 14-day RSI, and 52-Week Drawdown."""
    df = df.copy()
    df['20_EMA'] = df['Close'].ewm(span=20, adjust=False).mean()
    span_200 = min(200, len(df))
    df['200_EMA'] = df['Close'].ewm(span=span_200, adjust=False).mean()

    # 14-day RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))

    # 52-Week High & Drawdown
    df['52W_High'] = df['Close'].rolling(window=min(252, len(df)), min_periods=1).max()
    df['DD_52W'] = ((df['Close'] - df['52W_High']) / df['52W_High']) * 100.0
    return df

def get_latest_price(symbol: str) -> float:
    """Safely retrieves the most recent closing price."""
    df = fetch_ticker_data(symbol)
    if df is not None and not df.empty:
        return float(df['Close'].iloc[-1])
    return 0.0

# ==============================================================================
# 4. SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.header("🕹️ Strategy Controls")

all_symbols = sorted(list(set(
    list(st.session_state.engine1_core.keys()) +
    [t for theme in SWING_MATRIX.values() for t in theme] +
    DIP_CANDIDATES
)))

selected_symbol = st.sidebar.selectbox("Analyze Instrument", all_symbols, index=0)
auto_mode = st.sidebar.checkbox("Enable 3:15 PM Automated Guardrails", value=True)

if st.sidebar.button("Reset Portfolio to Baseline (₹30L)"):
    st.session_state.balance = 2700000.0
    for k in st.session_state.engine1_core:
        st.session_state.engine1_core[k]["units"] = 0
        st.session_state.engine1_core[k]["avg_cost"] = 0.0
    st.session_state.engine2_swing = {}
    st.session_state.engine3_reserve = 300000.0
    st.session_state.trade_log = []
    st.sidebar.success("Reset portfolio to ₹30,00,000 baseline!")
    st.rerun()

# ==============================================================================
# 5. TECHNICAL ANALYSIS DISPLAY
# ==============================================================================
df_raw = fetch_ticker_data(selected_symbol)

if df_raw is not None and len(df_raw) >= 20:
    df = calculate_indicators(df_raw)
    latest_price = float(df['Close'].iloc[-1])
    prev_price = float(df['Close'].iloc[-2]) if len(df) > 1 else latest_price
    ema_20 = float(df['20_EMA'].iloc[-1])
    ema_200 = float(df['200_EMA'].iloc[-1])
    latest_rsi = float(df['RSI'].iloc[-1])

    # Guardrail rules
    regime_shield = (latest_price > ema_20) and (latest_price > ema_200)

    # Top Metric Bar
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Deployable Working Balance", f"₹{st.session_state.balance:,.2f}")
    m2.metric("Reserve Pool (LIQUIDBEES)", f"₹{st.session_state.engine3_reserve:,.2f}")
    m3.metric(f"Quote ({selected_symbol})", f"₹{latest_price:,.2f}", f"RSI: {latest_rsi:.1f}")
    m4.metric("200-EMA Regime Shield", "PASSED ✅" if regime_shield else "BLOCKED ❌", delta=f"EMA200: ₹{ema_200:,.1f}")

    # Interactive Chart View
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df['20_EMA'], line=dict(color='green', width=1.5), name='20 EMA'))
    fig.add_trace(go.Scatter(x=df.index, y=df['200_EMA'], line=dict(color='red', width=2), name='200 EMA Shield'))
    fig.update_layout(
        title=f"{selected_symbol} Technical Regime & Guardrail Analysis",
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=40, b=20),
        height=380
    )
    st.plotly_chart(fig, use_container_width=True)

    # ==============================================================================
    # 6. PORTFOLIO ENGINE TABS
    # ==============================================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "Engine 1: 4-Pillar Core (50%)", 
        "Engine 2: Tactical Swing (40%)", 
        "Engine 3: Opportunity Reserve & Bottom Fishing (10%)",
        "Execution Audit Log"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: 4-PILLAR CORE WEALTH ENGINE
    # --------------------------------------------------------------------------
    with tab1:
        st.subheader("Engine 1: 4-Pillar Factor Core Basket (₹15,00,000 Rollout)")
        st.caption("Allocations: MOM30 (30%), MID150 (26.7%), JUNIOR (23.3%), MON100 (20%) — Tranche: ₹1.5L/month")

        core_records = []
        for k, v in st.session_state.engine1_core.items():
            curr_p = get_latest_price(k)
            invested = v["units"] * v["avg_cost"]
            cur_val = v["units"] * curr_p
            pnl = cur_val - invested

            core_records.append({
                "ETF": k,
                "Factor/Index": v["name"],
                "Units": v["units"],
                "Avg Cost": round(v["avg_cost"], 2),
                "CMP": round(curr_p, 2),
                "Invested (₹)": round(invested, 2),
                "Current Value (₹)": round(cur_val, 2),
                "P&L (₹)": round(pnl, 2),
                "Monthly Tranche": f"₹{v['target_tranche']:,.0f}"
            })

        st.dataframe(pd.DataFrame(core_records), use_container_width=True)

        if st.button("🚀 Execute Monthly Core Tranche (₹1,50,000)"):
            needed = sum(v["target_tranche"] for v in st.session_state.engine1_core.values())
            if st.session_state.balance < needed:
                st.error(f"Insufficient working balance! Needed: ₹{needed:,.2f}, Available: ₹{st.session_state.balance:,.2f}")
            else:
                for etf, v in st.session_state.engine1_core.items():
                    price = get_latest_price(etf)
                    if price > 0:
                        qty = int(v["target_tranche"] // price)
                        cost = qty * price
                        st.session_state.balance -= cost
                        
                        prev_u = v["units"]
                        prev_c = v["avg_cost"]
                        new_u = prev_u + qty
                        new_c = ((prev_u * prev_c) + cost) / new_u if new_u > 0 else price
                        
                        st.session_state.engine1_core[etf]["units"] = new_u
                        st.session_state.engine1_core[etf]["avg_cost"] = new_c

                        st.session_state.trade_log.append({
                            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Engine": "Core-Wealth",
                            "ETF": etf,
                            "Action": "MONTHLY_SIP_BUY",
                            "Qty": qty,
                            "Price": round(price, 2)
                        })
                st.success("Successfully deployed monthly 4-Pillar Core tranche!")
                st.rerun()

    # --------------------------------------------------------------------------
    # TAB 2: TACTICAL SWING ENGINE
    # --------------------------------------------------------------------------
    with tab2:
        st.subheader("Engine 2: Tactical Swing 5x4 Matrix (₹12,00,000 Allocation)")
        sw_col1, sw_col2 = st.columns([2, 1])

        with sw_col1:
            st.markdown("#### Active Swing Positions")
            swing_records = []
            for k, v in st.session_state.engine2_swing.items():
                curr_p = get_latest_price(k)
                invested = v["units"] * v["avg_cost"]
                cur_val = v["units"] * curr_p
                pct_return = ((cur_val - invested) / invested * 100) if invested > 0 else 0.0

                swing_records.append({
                    "ETF": k,
                    "Theme": v["theme"],
                    "Units": v["units"],
                    "Avg Cost": round(v["avg_cost"], 2),
                    "CMP": round(curr_p, 2),
                    "Peak Price": round(v.get("peak_price", curr_p), 2),
                    "Return (%)": round(pct_return, 2)
                })
            if swing_records:
                st.dataframe(pd.DataFrame(swing_records), use_container_width=True)
            else:
                st.info("No active swing positions open.")

        with sw_col2:
            st.markdown("#### Deploy Swing Tranche (₹60,000)")
            sw_theme = st.selectbox("Select Theme", list(SWING_MATRIX.keys()))
            sw_etf = st.selectbox("Select Target ETF", SWING_MATRIX[sw_theme])

            if st.button(f"Acquire Tranche: {sw_etf}"):
                etf_df = fetch_ticker_data(sw_etf)
                if etf_df is not None and len(etf_df) >= 20:
                    etf_df = calculate_indicators(etf_df)
                    cur_close = float(etf_df['Close'].iloc[-1])
                    cur_ema20 = float(etf_df['20_EMA'].iloc[-1])
                    cur_ema200 = float(etf_df['200_EMA'].iloc[-1])

                    # 200-EMA Guardrail check
                    if (cur_close < cur_ema200) or (cur_close < cur_ema20):
                        st.error(f"Execution Blocked! {sw_etf} is below 200-EMA/20-EMA regime shield.")
                    else:
                        tranche_val = 60000.0
                        qty = int(tranche_val // cur_close)
                        cost = qty * cur_close

                        if st.session_state.balance >= cost:
                            st.session_state.balance -= cost
                            prev_pos = st.session_state.engine2_swing.get(sw_etf, {
                                "units": 0, "avg_cost": 0.0, "theme": sw_theme, "peak_price": cur_close
                            })
                            new_u = prev_pos["units"] + qty
                            new_c = ((prev_pos["units"] * prev_pos["avg_cost"]) + cost) / new_u

                            st.session_state.engine2_swing[sw_etf] = {
                                "units": new_u,
                                "avg_cost": new_c,
                                "theme": sw_theme,
                                "peak_price": max(prev_pos.get("peak_price", cur_close), cur_close)
                            }
                            st.session_state.trade_log.append({
                                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "Engine": "Tactical-Swing",
                                "ETF": sw_etf,
                                "Action": "TRANCHE_BUY",
                                "Qty": qty,
                                "Price": round(cur_close, 2)
                            })
                            st.success(f"Acquired {qty} units of {sw_etf}!")
                            st.rerun()
                        else:
                            st.error("Insufficient working liquidity.")

        st.markdown("---")
        st.markdown("#### ⚡ 3:15 PM Automated Guardrails & Siphon Routine")
        if st.button("Run 3:15 PM Scan (Harvest +25% Winners & Execute Stops)"):
            scanned_actions = 0
            for sym, pos in list(st.session_state.engine2_swing.items()):
                p = get_latest_price(sym)
                cost = pos["avg_cost"]
                units = pos["units"]
                peak = max(pos.get("peak_price", p), p)
                st.session_state.engine2_swing[sym]["peak_price"] = peak
                gain_pct = (p - cost) / cost if cost > 0 else 0.0

                # RULE 1: +25% Momentum Harvest -> Siphon 50% profits directly to Engine 3 Reserve
                if gain_pct >= 0.25 and units > 1:
                    harvest_qty = units // 2
                    harvest_cash = harvest_qty * p
                    st.session_state.engine3_reserve += harvest_cash
                    st.session_state.engine2_swing[sym]["units"] = units - harvest_qty
                    st.session_state.trade_log.append({
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Engine": "Swing-Harvest",
                        "ETF": sym,
                        "Action": "PROFIT_SIPHON_TO_RESERVE",
                        "Qty": harvest_qty,
                        "Price": round(p, 2)
                    })
                    st.info(f"Siphoned ₹{harvest_cash:,.2f} from {sym} to Engine 3 Reserve!")
                    scanned_actions += 1

                # RULE 2: Trailing Stop Loss from Peak
                stop_threshold = TRAILING_STOPS.get(pos["theme"], 0.07)
                drawdown_from_peak = (p - peak) / peak if peak > 0 else 0.0
                if drawdown_from_peak <= -stop_threshold:
                    liquidation_cash = units * p
                    st.session_state.balance += liquidation_cash
                    del st.session_state.engine2_swing[sym]
                    st.session_state.trade_log.append({
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Engine": "Swing-Stop",
                        "ETF": sym,
                        "Action": "TRAILING_STOP_EXIT",
                        "Qty": units,
                        "Price": round(p, 2)
                    })
                    st.warning(f"Trailing Stop Triggered on {sym}. Position liquidated at ₹{p:,.2f}.")
                    scanned_actions += 1

            if scanned_actions == 0:
                st.write("All swing positions are within nominal guardrails.")
            else:
                st.rerun()

    # --------------------------------------------------------------------------
    # TAB 3: OPPORTUNITY RESERVE & BOTTOM FISHING
    # --------------------------------------------------------------------------
    with tab3:
        st.subheader("Engine 3: Opportunity Reserve & Automated Bottom Fishing")
        r1, r2, r3 = st.columns(3)
        r1.metric("LIQUIDBEES Reserve Balance", f"₹{st.session_state.engine3_reserve:,.2f}")
        r2.metric("Hard Capital Floor", f"₹{RESERVE_FLOOR:,.2f}")
        excess_ammo = max(0.0, st.session_state.engine3_reserve - RESERVE_FLOOR)
        r3.metric("Deployable Dip Ammo", f"₹{excess_ammo:,.2f}")

        st.markdown("---")
        st.markdown("### 🎣 Automated Bottom-Fishing Scanner (Grade-A Oversold Candidates)")
        st.caption("Triggers: RSI < 35 AND Drawdown ≥ 8% from 52W High AND Green Daily Reversal Confirmation.")

        dip_scan = []
        for d_sym in DIP_CANDIDATES:
            d_df = fetch_ticker_data(d_sym)
            if d_df is not None and len(d_df) >= 30:
                d_df = calculate_indicators(d_df)
                last_row = d_df.iloc[-1]
                prev_row = d_df.iloc[-2]

                rsi_val = last_row['RSI']
                dd_val = last_row['DD_52W']
                reversal_green = last_row['Close'] > prev_row['Close']

                is_deep_dip = (rsi_val < 35) and (dd_val <= -8.0) and reversal_green
                status = "🟢 STRONG DIP BUY" if is_deep_dip else \
                         "🟡 WATCHLIST (Oversold)" if (rsi_val < 40 or dd_val <= -8.0) else "⚪ NEUTRAL"

                dip_scan.append({
                    "ETF": d_sym,
                    "Price (₹)": round(last_row['Close'], 2),
                    "RSI(14)": round(rsi_val, 1),
                    "52W Drawdown": f"{dd_val:.1f}%",
                    "Target 20-EMA": round(last_row['20_EMA'], 2),
                    "Signal": status
                })

        st.dataframe(pd.DataFrame(dip_scan), use_container_width=True)

        st.markdown("#### Deploy Dip Ammo (₹50,000 Tranche from Reserve Surplus)")
        target_dip_etf = st.selectbox("Select Dip Target", DIP_CANDIDATES)

        if st.button(f"🎣 Execute Bottom-Fishing Buy: {target_dip_etf}"):
            tranche_size = 50000.0
            if excess_ammo < tranche_size:
                st.error(f"Cannot breach Reserve Floor! Available Ammo: ₹{excess_ammo:,.2f} (Floor: ₹{RESERVE_FLOOR:,.2f})")
            else:
                p_dip = get_latest_price(target_dip_etf)
                if p_dip > 0:
                    dip_units = int(tranche_size // p_dip)
                    dip_cost = dip_units * p_dip
                    st.session_state.engine3_reserve -= dip_cost

                    prev_dip = st.session_state.engine2_swing.get(target_dip_etf, {
                        "units": 0, "avg_cost": 0.0, "theme": "Dip-Fishing", "peak_price": p_dip
                    })
                    new_u = prev_dip["units"] + dip_units
                    new_c = ((prev_dip["units"] * prev_dip["avg_cost"]) + dip_cost) / new_u

                    st.session_state.engine2_swing[target_dip_etf] = {
                        "units": new_u,
                        "avg_cost": new_c,
                        "theme": "Dip-Fishing",
                        "peak_price": max(prev_dip.get("peak_price", p_dip), p_dip)
                    }

                    st.session_state.trade_log.append({
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Engine": "Reserve-Dip",
                        "ETF": target_dip_etf,
                        "Action": "BOTTOM_FISH_BUY",
                        "Qty": dip_units,
                        "Price": round(p_dip, 2)
                    })
                    st.success(f"Deployed ₹{dip_cost:,.2f} into {target_dip_etf} at ₹{p_dip:.2f} using Reserve Pool!")
                    st.rerun()

    # --------------------------------------------------------------------------
    # TAB 4: AUDIT LOG
    # --------------------------------------------------------------------------
    with tab4:
        st.subheader("Execution Audit Log & Blotter")
        if st.session_state.trade_log:
            st.dataframe(pd.DataFrame(st.session_state.trade_log).iloc[::-1], use_container_width=True)
        else:
            st.info("No trades executed yet.")

else:
    st.warning("Fetching market data or selected ticker has insufficient history. Please refresh.")
