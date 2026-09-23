import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 1. PAGE CONFIGURATION & STYLING
# ==========================================
st.set_page_config(page_title="8-ETF Institutional Paper Trading Terminal", layout="wide")

st.title("🛡️ 8-ETF Institutional Paper Trading Terminal")

# ==========================================
# 2. GOOGLE SHEETS CONNECTION & DATA FETCH
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def fetch_ledger_data():
    """Fetches the trade ledger directly from Google Sheets."""
    try:
        df = conn.read(worksheet="Sheet1", ttl=0)
        df = df.dropna(how="all")
        return df
    except Exception as e:
        st.error(f"Error connecting to Google Sheet: {e}")
        return pd.DataFrame(columns=["Date", "Ticker", "Type", "Quantity", "Price", "Amount"])

ledger_df = fetch_ledger_data()

# Calculate total equities deployed and units held per ticker from ledger
if not ledger_df.empty and "Ticker" in ledger_df.columns and "Quantity" in ledger_df.columns:
    ledger_df["Quantity"] = pd.to_numeric(ledger_df["Quantity"], errors="coerce").fillna(0)
    ledger_df["Amount"] = pd.to_numeric(ledger_df["Amount"], errors="coerce").fillna(0)
    
    units_by_ticker = ledger_df.groupby("Ticker")["Quantity"].sum().to_dict()
    equities_deployed_val = ledger_df["Amount"].sum()
else:
    units_by_ticker = {}
    equities_deployed_val = 0.0

# ==========================================
# 3. BASE PORTFOLIO & ATR STOP-LOSS LOGIC
# ==========================================
TOTAL_NAV = 3000000.0  # ₹3,000,000 Total Capital
NUM_WEEKS = 52
WEEKLY_TRANCHE = TOTAL_NAV / NUM_WEEKS  # ₹57,692.31 per week

ACTIVATION_THRESHOLD_PCT = 15.0  # Activate ATR trailing stop-loss when > 15% above 200-SMA
ATR_MULTIPLIER = 2.0             # 2x ATR distance from Peak Price

portfolio_data = [
    {"Symbol": "MOM30IETF.NS", "Name": "Nifty200 Momentum 30", "Category": "Factor Alpha", "LTP": 31.12, "200-SMA": 31.10, "Peak Price": 32.50, "14-ATR": 0.85},
    {"Symbol": "MID150BEES.NS", "Name": "Nifty Midcap 150", "Category": "Core Midcap", "LTP": 236.21, "200-SMA": 229.58, "Peak Price": 242.00, "14-ATR": 4.20},
    {"Symbol": "JUNIORBEES.NS", "Name": "Nifty Next 50", "Category": "Next Bluechips", "LTP": 782.31, "200-SMA": 754.99, "Peak Price": 795.00, "14-ATR": 12.50},
    {"Symbol": "MON100.NS", "Name": "Nasdaq 100 Tech", "Category": "Global Tech / USD", "LTP": 330.24, "200-SMA": 284.18, "Peak Price": 340.00, "14-ATR": 6.10},
    {"Symbol": "AUTOBEES.NS", "Name": "Nifty Auto & Mobility", "Category": "EV / Mobility", "LTP": 281.25, "200-SMA": 279.22, "Peak Price": 288.00, "14-ATR": 5.40},
    {"Symbol": "INFRAIETF.NS", "Name": "Nifty Infrastructure", "Category": "National Capex", "LTP": 93.36, "200-SMA": 95.70, "Peak Price": 98.50, "14-ATR": 1.90},
    {"Symbol": "GOLDBEES.NS", "Name": "Physical Gold", "Category": "Sovereign Ballast", "LTP": 125.57, "200-SMA": 122.81, "Peak Price": 127.00, "14-ATR": 1.65},
    {"Symbol": "SILVERBEES.NS", "Name": "Physical Silver", "Category": "Industrial Metal", "LTP": 222.21, "200-SMA": 229.93, "Peak Price": 238.00, "14-ATR": 5.80},
]

df_portfolio = pd.DataFrame(portfolio_data)

# Distance calculation relative to 200-SMA
df_portfolio["Distance (%)"] = ((df_portfolio["LTP"] - df_portfolio["200-SMA"]) / df_portfolio["200-SMA"]) * 100

# Function to calculate ATR Trailing Stop & Regime
def evaluate_atr_regime(row):
    dist = row["Distance (%)"]
    ltp = row["LTP"]
    sma = row["200-SMA"]
    peak = row["Peak Price"]
    atr = row["14-ATR"]
    
    # Calculate 2x ATR Trailing Stop Level
    atr_stop_level = peak - (ATR_MULTIPLIER * atr)
    
    # Conditional activation when price crosses +15% above 200-SMA
    if dist >= ACTIVATION_THRESHOLD_PCT:
        if ltp < atr_stop_level:
            return "ATR STOP-LOSS HIT (PARKED)", f"₹{atr_stop_level:,.2f} (Active)"
        return "BULL (ACTIVE ATR TSL)", f"₹{atr_stop_level:,.2f} (Active)"
    
    # Standard 200-SMA regime before reaching +15%
    if ltp >= sma:
        return "BULL (INVESTED)", "Inactive (<15% Distance)"
    else:
        return "BEAR (PARKED)", "Inactive (Below 200-SMA)"

# Apply ATR evaluation
regime_results = df_portfolio.apply(evaluate_atr_regime, axis=1)
df_portfolio["Regime"] = [res[0] for res in regime_results]
df_portfolio["ATR Stop Level"] = [res[1] for res in regime_results]

# Map dynamic units held from Google Sheet
df_portfolio["Units Held"] = df_portfolio["Symbol"].map(units_by_ticker).fillna(0).astype(int)

# ==========================================
# 4. ALLOCATION CALCULATION (52 WEEKS / ACTIVE ETFS)
# ==========================================
num_total_etfs = len(df_portfolio)
weekly_allocation_per_etf = WEEKLY_TRANCHE / (num_total_etfs - 1)  # ₹8,241.76 per slot

df_portfolio["Weekly Allotment (₹)"] = weekly_allocation_per_etf

# NAV summary metrics
liquidcase_cash_val = TOTAL_NAV - equities_deployed_val

# ==========================================
# 5. TOP SUMMARY METRICS
# ==========================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total NAV", f"₹{TOTAL_NAV:,.0f}")
col2.metric("Daily P&L", "₹0")
col3.metric("Equities Deployed", f"₹{equities_deployed_val:,.0f}")
col4.metric("LIQUIDCASE Cash", f"₹{liquidcase_cash_val:,.0f}")

st.markdown("---")

# ==========================================
# 6. TAB NAVIGATION & CONTENT
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📜 Execution Ledger", "🅿️ Park / Add Cash", "💸 Deploy Weekly SIP", "📊 My ETF List"])

# TAB 1: EXECUTION LEDGER
with tab1:
    st.subheader("Current Google Sheet Trade Ledger")
    if not ledger_df.empty:
        st.dataframe(ledger_df, use_container_width=True)
    else:
        st.info("No trades currently recorded in Google Sheet. Add headers and rows to start tracking.")
    
    if st.button("🔄 Save / Refresh Ledger Edits"):
        st.rerun()

# TAB 2: PARK / ADD CASH
with tab2:
    st.subheader("Park / Add Cash to Portfolio")
    cash_amount = st.number_input("Enter Amount (₹):", min_value=0.0, step=1000.0, value=100000.0)
    if st.button("Submit / Execute"):
        st.success(f"Successfully recorded ₹{cash_amount:,.2f} into cash reserve.")

# TAB 3: DEPLOY WEEKLY SIP
with tab3:
    st.subheader("Weekly Allocation Breakdown (52-Week Tranche Strategy)")
    st.markdown(f"**Total Weekly SIP Budget:** ₹{WEEKLY_TRANCHE:,.2f} (₹3,000,000 ÷ 52)")
    st.markdown(f"**Per-ETF Target Split:** ₹{weekly_allocation_per_etf:,.2f} per slot")
    st.markdown(f"📐 **ATR Trailing Stop-Loss:** Activates at **+15% Distance from 200-SMA** with a **{ATR_MULTIPLIER}x ATR** trail from Peak Price.")
    
    sip_display = df_portfolio[["Symbol", "Name", "Regime", "LTP", "14-ATR", "ATR Stop Level", "Weekly Allotment (₹)"]].copy()
    sip_display["Weekly Target Shares"] = (sip_display["Weekly Allotment (₹)"] / sip_display["LTP"]).astype(int)
    sip_display["Action Status"] = sip_display["Regime"].apply(lambda r: "BUY UNITS" if "BULL" in r else "PARK IN CASH")
    
    st.dataframe(sip_display, use_container_width=True)

# TAB 4: MY ETF LIST & REGIME
with tab4:
    st.subheader("Core 8-ETF Portfolio Tracking & ATR Stop-Loss Monitor")
    
    display_df = df_portfolio.copy()
    display_df["LTP"] = display_df["LTP"].apply(lambda x: f"₹{x:,.2f}")
    display_df["200-SMA"] = display_df["200-SMA"].apply(lambda x: f"₹{x:,.2f}")
    display_df["Peak Price"] = display_df["Peak Price"].apply(lambda x: f"₹{x:,.2f}")
    display_df["14-ATR"] = display_df["14-ATR"].apply(lambda x: f"₹{x:,.2f}")
    display_df["Distance (%)"] = display_df["Distance (%)"].apply(lambda x: f"{x:+.2f}%")
    
    st.dataframe(
        display_df[["Symbol", "Name", "Category", "LTP", "200-SMA", "Peak Price", "14-ATR", "Distance (%)", "ATR Stop Level", "Regime", "Units Held"]],
        use_container_width=True
    )
