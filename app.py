import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import json
import os

# ==============================================================================
# 1. PAGE SETUP & PERMANENT STATE PERSISTENCE ENGINE
# ==============================================================================
st.set_page_config(page_title="Master Strategy Blueprint v3.0", layout="wide", page_icon="🛡️")
st.title("🛡️ Master Strategy Blueprint v3.0 — Production Engine")

RESERVE_FLOOR = 200000.0  # ₹2,00,000 Hard Reserve Floor in LIQUIDCASE
DATA_FILE = "portfolio_data.json"

def load_portfolio():
    """Loads saved portfolio state from disk if it exists."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_portfolio():
    """Saves current portfolio state to disk."""
    state_to_save = {
        "balance": st.session_state.balance,
        "engine1_core": st.session_state.engine1_core,
        "engine2_swing": st.session_state.engine2_swing,
        "engine3_reserve": st.session_state.engine3_reserve,
        "trade_log": st.session_state.trade_log
    }
    with open(DATA_FILE, "w") as f:
        json.dump(state_to_save, f, indent=4, default=str)

# Initialize Session State from Permanent Storage
saved_data = load_portfolio()

if "balance" not in st.session_state:
    if saved_data:
        st.session_state.balance = saved_data.get("balance", 2700000.0)
        st.session_state.engine1_core = saved_data.get("engine1_core", {})
        st.session_state.engine2_swing = saved_data.get("engine2_swing", {})
        st.session_state.engine3_reserve = saved_data.get("engine3_reserve", 300000.0)
        st.session_state.trade_log = saved_data.get("trade_log", [])
    else:
        st.session_state.balance = 2700000.0
        st.session_state.engine1_core = {
            "MOM30IETF.NS":  {"units": 0, "avg_cost": 0.0, "target_tranche": 45000.0, "name": "Nifty200 Momentum 30"},
            "MID150BEES.NS": {"units": 0, "avg_cost": 0.0, "target_tranche": 40000.0, "name": "Nifty Midcap 150"},
            "JUNIORBEES.NS": {"units": 0, "avg_cost": 0.0, "target_tranche": 35000.0, "name": "Nifty Next 50"},
            "MON100.NS":     {"units": 0, "avg_cost": 0.0, "target_tranche": 30000.0, "name": "Nasdaq 100 Global Tech"}
        }
        st.session_state.engine2_swing = {}
        st.session_state.engine3_reserve = 300000.0
        st.session_state.trade_log = []
        save_portfolio()

# ==============================================================================
# 2. SWING MATRIX: ASCENDING VOLUME (Lowest -> Largest / King)
# ==============================================================================
SWING_MATRIX = {
    "Gold": ["ICICIGOLD.NS", "HDFCGOLD.NS", "TATAGOLD.NS", "GOLDBEES.NS"],
    "Silver": ["HDFCSILVER.NS", "SILVERIETF.NS", "TATSILV.NS", "SILVERBEES.NS"],
    "Banking": ["SETFNIFBK.NS", "PSUBNKBEES.NS", "BANKBEES.NS"],
    "IT": ["ITIETF.NS", "ITBEES.NS"],
    "Auto": ["AUTOBEES.NS"],
    "Defence/PSU": ["MODEFENCE.NS", "CPSEETF.NS"]
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
# 3. CACHED DATA & TECHNICAL INDICATOR ENGINE
# ==============================================================================
@st.cache_data(ttl=300)
def fetch_ticker_data(symbol: str):
    """Fetches historical daily bars with error resilience."""
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
    save_portfolio()
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

    regime_shield = (latest_price > ema_20) and (latest_price > ema_200)

    # Top Metric Bar
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Deployable Working Balance", f"₹{st.session_state.balance:,.2f}")
    m2.metric("Reserve Pool (LIQUIDCASE)", f"₹{st.session_state.engine3_reserve:,.2f}")
    m3.metric(f"Quote ({selected_symbol})", f"₹{latest_price:,.2f}", f"RSI: {latest_rsi:.1f}")
    m4.metric("Regime Shield", "PASSED ✅" if regime_shield else "BLOCKED ❌", delta=f"20-EMA: ₹{ema_20:,.1f} | 200-EMA: ₹{ema_200:,.1f}")
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
        "Engine 2: 4-Tier Pyramidal Swing (40%)", 
        "Engine 3: Opportunity Reserve & Deep-Down Buying (10%)",
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
                save_portfolio()
                st.success("Successfully deployed monthly 4-Pillar Core tranche!")
                st.rerun()

    # --------------------------------------------------------------------------
    # TAB 2: 4-TIER PYRAMIDAL SWING ENGINE (PYRAMID UP)
    # --------------------------------------------------------------------------
    with tab2:
        st.subheader("Engine 2: 4-Tier Pyramidal Swing Engine (₹12,00,000 Cap)")
        st.caption("Rules: ₹60k/tranche • Max 4 Tiers (₹2.4L/theme) • Only add to winners • Dynamic Break-Even Trailing")

        sw_col1, sw_col2 = st.columns([2, 1])

        with sw_col1:
            st.markdown("#### Active Pyramids")
            swing_records = []
            for k, v in st.session_state.engine2_swing.items():
                curr_p = get_latest_price(k)
                invested = v["units"] * v["avg_cost"]
                cur_val = v["units"] * curr_p
                pct_return = ((cur_val - invested) / invested * 100) if invested > 0 else 0.0

                swing_records.append({
                    "ETF": k,
                    "Theme": v["theme"],
                    "Pyramid Tier": f"Tier {v.get('tier', 1)} / 4",
                    "Units": v["units"],
                    "Avg Cost": round(v["avg_cost"], 2),
                    "CMP": round(curr_p, 2),
                    "Invested (₹)": round(invested, 2),
                    "P&L (%)": f"{pct_return:+.2f}%",
                    "Next Tier Eligible": "YES ✅" if (pct_return >= 2.5 and v.get('tier', 1) < 4) else "LOCKED 🔒"
                })

            if swing_records:
                st.dataframe(pd.DataFrame(swing_records), use_container_width=True)
            else:
                st.info("No active swing pyramids open. Select an ETF on the right to start Tier 1.")

        with sw_col2:
            st.markdown("#### Deploy / Scale Pyramid")
            sw_theme = st.selectbox("Select Theme", list(SWING_MATRIX.keys()))
            sw_etf = st.selectbox("Select Target ETF", SWING_MATRIX[sw_theme])

            pos = st.session_state.engine2_swing.get(sw_etf, None)
            curr_tier = pos.get("tier", 0) if pos else 0
            cur_p = get_latest_price(sw_etf)
            gain_pct = ((cur_p - pos["avg_cost"]) / pos["avg_cost"] * 100) if (pos and pos["avg_cost"] > 0) else 0.0

            next_tier = curr_tier + 1
            can_deploy = False
            status_msg = ""

            if curr_tier == 0:
                can_deploy = True
                status_msg = f"Ready for **Tier 1 Pilot Entry** (₹60,000)"
            elif curr_tier == 1:
                if gain_pct >= 2.5:
                    can_deploy = True
                    status_msg = f"Eligible for **Tier 2 Add** (+{gain_pct:.1f}% gain ✅)"
                else:
                    status_msg = f"⚠️ Tier 2 Locked: Need $\ge$+2.5% gain (Current: {gain_pct:+.1f}%)"
            elif curr_tier == 2:
                if gain_pct >= 6.0:
                    can_deploy = True
                    status_msg = f"Eligible for **Tier 3 Add** (+{gain_pct:.1f}% gain ✅)"
                else:
                    status_msg = f"⚠️ Tier 3 Locked: Need $\ge$+6.0% gain (Current: {gain_pct:+.1f}%)"
            elif curr_tier == 3:
                if gain_pct >= 10.0:
                    can_deploy = True
                    status_msg = f"Eligible for **Tier 4 Final Add** (+{gain_pct:.1f}% gain ✅)"
                else:
                    status_msg = f"⚠️ Tier 4 Locked: Need $\ge$+10.0% gain (Current: {gain_pct:+.1f}%)"
            else:
                status_msg = f"🔒 **Max Pyramid Reached (Tier 4 / ₹2,40,000 filled)**"

            st.info(status_msg)

            if next_tier <= 4 and st.button(f"Acquire Tier {next_tier} Tranche (₹60,000)"):
                if not can_deploy:
                    st.error("Pyramid rule violation: Cannot add to an unconfirmed or losing trade!")
                else:
                    etf_df = fetch_ticker_data(sw_etf)
                    if etf_df is not None and len(etf_df) >= 20:
                        etf_df = calculate_indicators(etf_df)
                        cur_close = float(etf_df['Close'].iloc[-1])
                        cur_ema20 = float(etf_df['20_EMA'].iloc[-1])
                        cur_ema200 = float(etf_df['200_EMA'].iloc[-1])

                        if curr_tier == 0 and ((cur_close < cur_ema200) or (cur_close < cur_ema20)):
                            st.error(f"Execution Blocked! {sw_etf} is below 200-EMA/20-EMA shield.")
                        else:
                            tranche_val = 60000.0
                            qty = int(tranche_val // cur_close)
                            cost = qty * cur_close

                            if st.session_state.balance >= cost:
                                st.session_state.balance -= cost
                                prev_units = pos["units"] if pos else 0
                                prev_cost = pos["avg_cost"] if pos else 0.0
                                new_u = prev_units + qty
                                new_c = ((prev_units * prev_cost) + cost) / new_u

                                st.session_state.engine2_swing[sw_etf] = {
                                    "units": new_u,
                                    "avg_cost": new_c,
                                    "theme": sw_theme,
                                    "tier": next_tier,
                                    "peak_price": max(pos.get("peak_price", cur_close) if pos else cur_close, cur_close)
                                }
                                st.session_state.trade_log.append({
                                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "Engine": f"Swing-Pyramid-T{next_tier}",
                                    "ETF": sw_etf,
                                    "Action": f"PYRAMID_BUY_T{next_tier}",
                                    "Qty": qty,
                                    "Price": round(cur_close, 2)
                                })
                                save_portfolio()
                                st.success(f"Successfully scaled into Tier {next_tier} for {sw_etf}!")
                                st.rerun()
                            else:
                                st.error("Insufficient working balance.")

        st.markdown("---")
        st.markdown("#### ⚡ 3:15 PM Automated Guardrails & Siphon Routine")
        if st.button("Run 3:15 PM Scan (Harvest +25% Winners & Execute Stops)"):
            scanned_actions = 0
            for sym, pos in list(st.session_state.engine2_swing.items()):
                p = get_latest_price(sym)
                cost = pos["avg_cost"]
                units = pos["units"]
                tier = pos.get("tier", 1)
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

                # RULE 2: Dynamic Pyramidal Trailing Stop
                base_stop = TRAILING_STOPS.get(pos["theme"], 0.07)
                drawdown_from_peak = (p - peak) / peak if peak > 0 else 0.0
                
                triggered = False
                if tier == 1 and drawdown_from_peak <= -base_stop:
                    triggered = True
                elif tier >= 2:
                    if p <= cost or drawdown_from_peak <= -0.05:
                        triggered = True

                if triggered:
                    liquidation_cash = units * p
                    st.session_state.balance += liquidation_cash
                    del st.session_state.engine2_swing[sym]
                    st.session_state.trade_log.append({
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Engine": "Swing-Pyramid-Stop",
                        "ETF": sym,
                        "Action": f"STOP_EXIT_T{tier}",
                        "Qty": units,
                        "Price": round(p, 2)
                    })
                    st.warning(f"Pyramid Exit Triggered on {sym} (Tier {tier}). Position closed at ₹{p:,.2f}.")
                    scanned_actions += 1

            if scanned_actions > 0:
                save_portfolio()
                st.rerun()
            else:
                st.write("All pyramid positions healthy. No stops or siphon levels breached.")

    # --------------------------------------------------------------------------
    # TAB 3: OPPORTUNITY RESERVE & DEEP-DOWN BUYING (PYRAMID DOWN)
    # --------------------------------------------------------------------------
    with tab3:
        st.subheader("Engine 3: Opportunity Reserve & Deep-Down Buying")
        st.caption("Quarantined crash reserve in LIQUIDCASE. Buys deep panic (RSI < 35, DD ≥ 8%) on Grade-A index giants.")
        
        r1, r2, r3 = st.columns(3)
        r1.metric("LIQUIDCASE Reserve Balance", f"₹{st.session_state.engine3_reserve:,.2f}")
        r2.metric("Hard Capital Floor", f"₹{RESERVE_FLOOR:,.2f}")
        excess_ammo = max(0.0, st.session_state.engine3_reserve - RESERVE_FLOOR)
        r3.metric("Deployable Dip Ammo", f"₹{excess_ammo:,.2f}")

        st.markdown("---")
        st.markdown("### 🎣 Automated Deep-Down Buying Scanner (Grade-A Index Giants Only)")
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
                    "Mean Reversion Target (20-EMA)": round(last_row['20_EMA'], 2),
                    "Signal": status
                })

        st.dataframe(pd.DataFrame(dip_scan), use_container_width=True)

        st.markdown("#### Deploy Dip Ammo (₹50,000 Tranche from Reserve Surplus)")
        target_dip_etf = st.selectbox("Select Dip Target", DIP_CANDIDATES)

        if st.button(f"🎣 Execute Deep-Down Buy: {target_dip_etf}"):
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
                    save_portfolio()
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
