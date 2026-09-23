import streamlit as st
import pandas as pd
import yfinance as yf
from streamlit_gsheets import GSheetsConnection

# ---------------------------------------------------------
# 1. PAGE SETUP & CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(
    page_title="8-ETF Institutional Paper Trading Terminal",
    layout="wide"
)

TOTAL_NAV = 3000000.0  # ₹3,000,000 Total Capital Base

# ---------------------------------------------------------
# 2. CONNECT TO GOOGLE SHEETS & FETCH LEDGER DATA
# ---------------------------------------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    ledger_df = conn.read(ttl=0)  # Live data without cache
except Exception as e:
    st.error(f"Error connecting to Google Sheet: {e}")
    ledger_df = pd.DataFrame()

# Clean and calculate net deployed capital & holdings
if not ledger_df.empty and "Ticker" in ledger_df.columns and "Amount" in ledger_df.columns:
    # Ensure numeric types and uppercase strings
    ledger_df["Quantity"] = pd.to_numeric(ledger_df["Quantity"], errors="coerce").fillna(0)
    ledger_df["Price"] = pd.to_numeric(ledger_df["Price"], errors="coerce").fillna(0)
    ledger_df["Amount"] = pd.to_numeric(ledger_df["Amount"], errors="coerce").fillna(0)
    ledger_df["Type"] = ledger_df["Type"].astype(str).str.upper().str.strip()

    # Net quantity per ticker (BUYs minus SELLs)
    buy_qty = ledger_df[ledger_df["Type"] == "BUY"].groupby("Ticker")["Quantity"].sum()
    sell_qty = ledger_df[ledger_df["Type"] == "SELL"].groupby("Ticker")["Quantity"].sum()
    units_by_ticker = buy_qty.subtract(sell_qty, fill_value=0).to_dict()

    # Net cash deployed in equities
    total_buys = ledger_df[ledger_df["Type"] == "BUY"]["Amount"].sum()
    total_sells = ledger_df[ledger_df["Type"] == "SELL"]["Amount"].sum()
    equities_deployed_val = total_buys - total_sells
else:
    units_by_ticker = {}
    equities_deployed_val = 0.0

# Dynamic cash deduction from total NAV
liquidcase_cash_val = TOTAL_NAV - equities_deployed_val

# ---------------------------------------------------------
# 3. HEADER METRICS DISPLAY
# ---------------------------------------------------------
st.title("8-ETF Institutional Paper Trading Terminal")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total NAV", f"₹{TOTAL_NAV:,.0f}")
col2.metric("Daily P&L", "₹0")
col3.metric("Equities Deployed", f"₹{equities_deployed_val:,.0f}")
col4.metric("LIQUIDCASE Cash", f"₹{liquidcase_cash_val:,.0f}")

st.divider()

# ---------------------------------------------------------
# 4. ETF PORTFOLIO & STRATEGY TABLE
# ---------------------------------------------------------
etf_data = [
    {"Symbol": "MOM30IETF.NS", "Name": "Nifty200 Momentum 30", "Regime": "BULL (INVESTED)", "LTP": 31.12, "14-ATR": 0.85, "ATR Stop Level": "Inactive (<15% Distance)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 264, "Action Status": "BUY UNITS"},
    {"Symbol": "MID150BEES.NS", "Name": "Nifty Midcap 150", "Regime": "BULL (INVESTED)", "LTP": 236.21, "14-ATR": 4.20, "ATR Stop Level": "Inactive (<15% Distance)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 34, "Action Status": "BUY UNITS"},
    {"Symbol": "JUNIORBEES.NS", "Name": "Nifty Next 50", "Regime": "BULL (INVESTED)", "LTP": 782.31, "14-ATR": 12.50, "ATR Stop Level": "Inactive (<15% Distance)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 10, "Action Status": "BUY UNITS"},
    {"Symbol": "MON100.NS", "Name": "Nasdaq 100 Tech", "Regime": "BULL (ACTIVE ATR TSL)", "LTP": 330.24, "14-ATR": 6.10, "ATR Stop Level": "₹327.80 (Active)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 24, "Action Status": "BUY UNITS"},
    {"Symbol": "AUTOBEES.NS", "Name": "Nifty Auto & Mobility", "Regime": "BULL (INVESTED)", "LTP": 281.25, "14-ATR": 5.40, "ATR Stop Level": "Inactive (<15% Distance)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 29, "Action Status": "BUY UNITS"},
    {"Symbol": "INFRAIETF.NS", "Name": "Nifty Infrastructure", "Regime": "BEAR (PARKED)", "LTP": 93.36, "14-ATR": 1.90, "ATR Stop Level": "Inactive (Below 200-SMA)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 88, "Action Status": "PARK IN CASH"},
    {"Symbol": "GOLDBEES.NS", "Name": "Physical Gold", "Regime": "BULL (INVESTED)", "LTP": 125.57, "14-ATR": 1.65, "ATR Stop Level": "Inactive (<15% Distance)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 65, "Action Status": "BUY UNITS"},
    {"Symbol": "SILVERBEES.NS", "Name": "Physical Silver", "Regime": "BEAR (PARKED)", "LTP": 222.21, "14-ATR": 5.80, "ATR Stop Level": "Inactive (Below 200-SMA)", "Weekly Allotment (₹)": 8241.7582, "Weekly Target Shares": 37, "Action Status": "PARK IN CASH"},
]

st.subheader("Weekly Allocation Breakdown (52-Week Tranche Strategy)")
st.caption(f"Total Weekly SIP Budget: ₹{TOTAL_NAV/52:,.2f} (₹{TOTAL_NAV:,.0f} ÷ 52)")
st.caption(f"Per-ETF Target Split: ₹{(TOTAL_NAV/52)/8:,.2f} per slot")

etf_df = pd.DataFrame(etf_data)
st.dataframe(etf_df, use_container_width=True)

# ---------------------------------------------------------
# 5. EXECUTION LEDGER ENTRY FORM
# ---------------------------------------------------------
st.divider()
st.subheader("Log Trade Execution")

with st.form("log_trade_form"):
    col_a, col_b, col_c, col_d = st.columns(4)
    trade_date = col_a.date_input("Date")
    ticker = col_b.selectbox("Ticker", etf_df["Symbol"].tolist())
    trade_type = col_c.selectbox("Type", ["BUY", "SELL"])
    quantity = col_d.number_input("Quantity", min_value=1, step=1)

    price = st.number_input("Price (₹)", min_value=0.01, step=0.05)
    submit_trade = st.form_submit_button("Save Trade to Ledger")

    if submit_trade:
        amount = quantity * price
        new_entry = pd.DataFrame([{
            "Date": str(trade_date),
            "Ticker": ticker,
            "Type": trade_type,
            "Quantity": quantity,
            "Price": price,
            "Amount": amount
        }])

        updated_df = pd.concat([ledger_df, new_entry], ignore_index=True)
        try:
            conn.update(data=updated_df)
            st.success("Trade successfully logged! Refreshing calculations...")
            st.rerun()
        except Exception as err:
            st.error(f"Failed to save trade: {err}")
