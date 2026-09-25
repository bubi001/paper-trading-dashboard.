import streamlit as st
import pandas as pd
import yfinance as yf
from streamlit_gsheets import GSheetsConnection
from streamlit_autorefresh import st_autorefresh
st.set_page_config(page_title="8-ETF Institutional Paper Trading Terminal", layout="wide")

# Auto-refresh page every 60 seconds (60,000 ms)
st_autorefresh(interval=60000, key="price_feed_refresh")
# Target ETFs
TICKERS = [
    "MOM30IETF.NS", "MID150BEES.NS", "JUNIORBEES.NS", "MON100.NS",
    "AUTOBEES.NS", "INFRAIETF.NS", "GOLDBEES.NS", "SILVERBEES.NS"
]

EXPECTED_COLUMNS = ["Date", "Ticker", "Type", "Quantity", "Buy_Price", "Total_Amount"]

# -------------------------------------------------------------------
# 1. FETCH & MAP GOOGLE SHEET LEDGER
# -------------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def get_ledger_data():
    try:
        df = conn.read(ttl=10)
        if df is None or df.empty:
            return pd.DataFrame(columns=EXPECTED_COLUMNS)
        
        # Standardize column headers to handle variations (e.g. Price vs Buy_Price)
        column_mapping = {
            "Price": "Buy_Price",
            "Amount": "Total_Amount",
            "Symbol": "Ticker",
            "Action": "Type"
        }
        df = df.rename(columns=column_mapping)
        
        # Fill missing required columns if necessary
        for col in EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = None
                
        return df[EXPECTED_COLUMNS]
    except Exception:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

ledger_df = get_ledger_data()

# -------------------------------------------------------------------
# 2. LIVE MARKET PRICES & DAILY P&L CALCULATION
# -------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_live_prices(tickers):
    prices = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            prices[t] = {
                "live_price": info.get("lastPrice", 0.0),
                "prev_close": info.get("previousClose", 0.0)
            }
        except Exception:
            prices[t] = {"live_price": 0.0, "prev_close": 0.0}
    return prices

live_data = fetch_live_prices(TICKERS)
INITIAL_CASH = 3000000.00  # ₹3,000,000 baseline NAV

if not ledger_df.empty:
    # Ensure numeric conversion for sheet values
    ledger_df["Quantity"] = pd.to_numeric(ledger_df["Quantity"], errors="coerce").fillna(0)
    ledger_df["Buy_Price"] = pd.to_numeric(ledger_df["Buy_Price"], errors="coerce").fillna(0)
    ledger_df["Total_Amount"] = pd.to_numeric(ledger_df["Total_Amount"], errors="coerce").fillna(0)

    # Filter BUY trades
    buy_trades = ledger_df[ledger_df["Type"].astype(str).str.upper() == "BUY"]

    if not buy_trades.empty:
        # Group executed trades by Ticker
        holdings = buy_trades.groupby("Ticker").agg({
            "Quantity": "sum",
            "Total_Amount": "sum"
        }).reset_index()

        holdings["Live_Price"] = holdings["Ticker"].map(lambda x: live_data.get(x, {}).get("live_price", 0.0))
        holdings["Prev_Close"] = holdings["Ticker"].map(lambda x: live_data.get(x, {}).get("prev_close", 0.0))
        
        holdings["Current_Value"] = holdings["Quantity"] * holdings["Live_Price"]
        holdings["Daily_PnL"] = holdings["Quantity"] * (holdings["Live_Price"] - holdings["Prev_Close"])

        equities_deployed = holdings["Current_Value"].sum()
        daily_pnl = holdings["Daily_PnL"].sum()
        total_cost = holdings["Total_Amount"].sum()
        liquidcase_cash = INITIAL_CASH - total_cost
    else:
        equities_deployed, daily_pnl, liquidcase_cash = 0.0, 0.0, INITIAL_CASH
else:
    equities_deployed, daily_pnl, liquidcase_cash = 0.0, 0.0, INITIAL_CASH

total_nav = liquidcase_cash + equities_deployed
# Calculate Total P&L
total_pl = total_current_value - equities_deployed
# -------------------------------------------------------------------
# 3. METRICS DISPLAY
# -------------------------------------------------------------------
st.title("8-ETF Institutional Paper Trading Terminal")
 
col1, col2, col3, col4, col5 = st.columns(5)
with col3:
    st.metric(
        label="Total P&L",
        value=f"₹{total_pl:,.2f}",
        delta=f"₹{total_pl:,.2f}"
    )
col1.metric("Total NAV", f"₹{total_nav:,.2f}")
col2.metric("Daily P&L", f"₹{daily_pnl:,.2f}", delta=f"₹{daily_pnl:,.2f}")
col3.metric("Equities Deployed", f"₹{equities_deployed:,.2f}")
col4.metric("LIQUIDCASE Cash", f"₹{liquidcase_cash:,.2f}")

st.markdown("---")

# -------------------------------------------------------------------
# 4. LIVE WATCHLIST & LEDGER DISPLAY
# -------------------------------------------------------------------
st.subheader("Live Portfolio Watchlist")
watchlist_df = pd.DataFrame([
    {
        "Symbol": ticker,
        "Live Market Price (₹)": live_data[ticker]["live_price"],
        "Previous Close (₹)": live_data[ticker]["prev_close"],
        "1-Day Change (₹)": round(live_data[ticker]["live_price"] - live_data[ticker]["prev_close"], 2)
    } for ticker in TICKERS
])
st.dataframe(watchlist_df, use_container_width=True)

st.subheader("Imported Google Sheets Trade Ledger")
st.dataframe(ledger_df, use_container_width=True)
