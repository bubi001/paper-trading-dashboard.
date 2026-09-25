import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
from datetime import datetime

st.set_page_config(
    page_title="8-ETF Institutional Paper Trading Terminal", 
    layout="wide"
)

# Auto-refresh page every 60 seconds
st_autorefresh(interval=60000, key="price_feed_refresh")

# Target ETFs
TICKERS = [
    "LIQUIDCASE.NS",
    "MOM30IETF.NS",
    "MID150BEES.NS",
    "JUNIORBEES.NS",
    "MON100.NS",
    "AUTOBEES.NS",
    "INFRAIETF.NS",
    "GOLDBEES.NS",
    "SILVERBEES.NS",
]

EXPECTED_COLUMNS = [
    "Date",
    "Ticker",
    "Type",
    "Quantity",
    "Buy_Price",
    "Total_Amount",
]

# -------------------------------------------------------------------
# 1. FETCH & MAP GOOGLE SHEET LEDGER
# -------------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def get_ledger_data():
    try:
        df = conn.read(ttl=10)
        if df is None or df.empty:
            return pd.DataFrame(columns=EXPECTED_COLUMNS)
        
        column_mapping = {
            "Price": "Buy_Price",
            "Amount": "Total_Amount",
            "Symbol": "Ticker",
            "Action": "Type",
        }
        df = df.rename(columns=column_mapping)
        
        for col in EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = None
                
        return df[EXPECTED_COLUMNS].dropna(how="all")
    except Exception:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

ledger_df = get_ledger_data()

# -------------------------------------------------------------------
# 2. LIVE MARKET PRICES & ETF HOLDINGS CALCULATION
# -------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_live_prices(tickers):
    prices = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).fast_info
            prices[t] = {
                "live_price": info.get("lastPrice", 0.0),
                "prev_close": info.get("previousClose", 0.0),
            }
        except Exception:
            prices[t] = {"live_price": 0.0, "prev_close": 0.0}
    return prices

live_data = fetch_live_prices(TICKERS)
TOTAL_CAPITAL = 3000000.00  # ₹30,00,000 baseline cash pool

if not ledger_df.empty:
    ledger_df["Quantity"] = pd.to_numeric(ledger_df["Quantity"], errors="coerce").fillna(0)
    ledger_df["Buy_Price"] = pd.to_numeric(ledger_df["Buy_Price"], errors="coerce").fillna(0)
    ledger_df["Total_Amount"] = pd.to_numeric(ledger_df["Total_Amount"], errors="coerce").fillna(0)
    
    buy_trades = ledger_df[ledger_df["Type"].astype(str).str.upper() == "BUY"]
    sell_trades = ledger_df[ledger_df["Type"].astype(str).str.upper() == "SELL"]
    
    if not buy_trades.empty:
        buy_grouped = buy_trades.groupby("Ticker").agg({"Quantity": "sum", "Total_Amount": "sum"}).reset_index()
        
        if not sell_trades.empty:
            sell_grouped = sell_trades.groupby("Ticker").agg({"Quantity": "sum", "Total_Amount": "sum"}).reset_index()
            holdings = pd.merge(buy_grouped, sell_grouped, on="Ticker", how="left", suffixes=("_buy", "_sell")).fillna(0)
            holdings["Quantity"] = holdings["Quantity_buy"] - holdings["Quantity_sell"]
            holdings["Total_Amount"] = holdings["Total_Amount_buy"] - holdings["Total_Amount_sell"]
        else:
            holdings = buy_grouped

        holdings = holdings[holdings["Quantity"] > 0].copy()
    else:
        holdings = pd.DataFrame(columns=["Ticker", "Quantity", "Total_Amount"])
else:
    holdings = pd.DataFrame(columns=["Ticker", "Quantity", "Total_Amount"])

# Separate active equity holdings from LIQUIDCASE
equity_holdings = holdings[holdings["Ticker"] != "LIQUIDCASE.NS"].copy()
equity_cost = equity_holdings["Total_Amount"].sum() if not equity_holdings.empty else 0.0

# Extract explicit LIQUIDCASE trades from ledger
lc_trade_row = holdings[holdings["Ticker"] == "LIQUIDCASE.NS"]
explicit_lc_units = lc_trade_row["Quantity"].sum() if not lc_trade_row.empty else 0
explicit_lc_cost = lc_trade_row["Total_Amount"].sum() if not lc_trade_row.empty else 0.0

lc_live_price = live_data.get("LIQUIDCASE.NS", {}).get("live_price", 100.0)
lc_prev_close = live_data.get("LIQUIDCASE.NS", {}).get("prev_close", 100.0)

# Calculate uninvested cash to auto-park
uninvested_cash = max(0.0, TOTAL_CAPITAL - equity_cost - explicit_lc_cost)
auto_parked_lc_units = uninvested_cash / lc_live_price if lc_live_price > 0 else 0

# Total LIQUIDCASE units (Ledger Trades + Auto-Parked Cash)
total_liquidcase_units = explicit_lc_units + auto_parked_lc_units
total_liquidcase_cost = explicit_lc_cost + uninvested_cash

# Calculate equity metrics
if not equity_holdings.empty:
    equity_holdings["Live_Price"] = equity_holdings["Ticker"].map(lambda x: live_data.get(x, {}).get("live_price", 0.0))
    equity_holdings["Prev_Close"] = equity_holdings["Ticker"].map(lambda x: live_data.get(x, {}).get("prev_close", 0.0))
    equity_holdings["Current_Value"] = equity_holdings["Quantity"] * equity_holdings["Live_Price"]
    equity_holdings["Daily_PnL"] = equity_holdings["Quantity"] * (equity_holdings["Live_Price"] - equity_holdings["Prev_Close"])
    equity_holdings["Total_PnL"] = equity_holdings["Current_Value"] - equity_holdings["Total_Amount"]
else:
    equity_holdings = pd.DataFrame(columns=["Ticker", "Quantity", "Total_Amount", "Live_Price", "Prev_Close", "Current_Value", "Daily_PnL", "Total_PnL"])

# Create LIQUIDCASE row with active Daily PnL
lc_current_value = total_liquidcase_units * lc_live_price
lc_daily_pnl = total_liquidcase_units * (lc_live_price - lc_prev_close)

lc_row = pd.DataFrame([{
    "Ticker": "LIQUIDCASE.NS",
    "Quantity": total_liquidcase_units,
    "Total_Amount": total_liquidcase_cost,
    "Live_Price": lc_live_price,
    "Prev_Close": lc_prev_close,
    "Current_Value": lc_current_value,
    "Daily_PnL": lc_daily_pnl,
    "Total_PnL": lc_current_value - total_liquidcase_cost
}])

holdings = pd.concat([equity_holdings, lc_row], ignore_index=True)

# Final aggregate metrics
total_portfolio_value = holdings["Current_Value"].sum()
daily_pnl = holdings["Daily_PnL"].sum()
total_pl = holdings["Total_PnL"].sum()

liquidcase_value = lc_current_value

# -------------------------------------------------------------------
# 3. METRICS DISPLAY
# -------------------------------------------------------------------
st.title("8-ETF Institutional Paper Trading Terminal")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total NAV", f"₹{total_portfolio_value:,.2f}")
col2.metric("Daily P&L", f"₹{daily_pnl:,.2f}", delta=f"{daily_pnl:,.2f}")
col3.metric("Total P&L", f"₹{total_pl:,.2f}", delta=f"{total_pl:,.2f}")
col4.metric("Equities Deployed", f"₹{equity_cost:,.2f}")
col5.metric("LIQUIDCASE Value", f"₹{liquidcase_value:,.2f}", delta=f"{int(total_liquidcase_units)} Units")

st.markdown("---")

# -------------------------------------------------------------------
# 4. TAB NAVIGATION & INTERFACE
# -------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📊 Portfolio & Watchlist", "📜 Trade Ledger", "➕ Import to Sheet"])

with tab1:
    st.subheader("Live Portfolio & ETF Holdings")
    
    if not holdings.empty:
        st.markdown("#### Current ETF Positions")
        holdings_display = holdings[["Ticker", "Quantity", "Total_Amount", "Live_Price", "Current_Value", "Daily_PnL", "Total_PnL"]].copy()
        holdings_display.columns = ["Ticker", "Units", "Cost Value (₹)", "Live Price (₹)", "Current Value (₹)", "1-Day P&L (₹)", "Total P&L (₹)"]
        st.dataframe(holdings_display, use_container_width=True)
    
    st.markdown("#### Market Watchlist")
    watchlist_df = pd.DataFrame([
        {
            "Symbol": ticker,
            "Live Market Price (₹)": live_data[ticker]["live_price"],
            "Previous Close (₹)": live_data[ticker]["prev_close"],
            "1-Day Change (₹)": round(
                live_data[ticker]["live_price"] - live_data[ticker]["prev_close"], 2
            ),
        }
        for ticker in TICKERS
    ])
    st.dataframe(watchlist_df, use_container_width=True)

with tab2:
    st.subheader("Imported Google Sheets Trade Ledger")
    st.dataframe(ledger_df, use_container_width=True)

with tab3:
    st.subheader("Import New Trade Entry to Google Sheets")
    
    with st.form("add_trade_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            trade_date = st.date_input("Date", datetime.today())
            ticker = st.selectbox("Ticker", TICKERS)
            trade_type = st.selectbox("Type", ["BUY", "SELL"])
        with col_b:
            quantity = st.number_input("Quantity", min_value=1, step=1, value=100)
            buy_price = st.number_input("Price (₹)", min_value=0.01, step=0.05, value=100.00)
            total_amount = quantity * buy_price
            st.write(f"**Total Amount:** ₹{total_amount:,.2f}")
            
        submitted = st.form_submit_button("Import Trade to Google Sheet")
        
        if submitted:
            new_row = pd.DataFrame([{
                "Date": str(trade_date),
                "Ticker": ticker,
                "Type": trade_type,
                "Quantity": quantity,
                "Buy_Price": buy_price,
                "Total_Amount": total_amount
            }])
            
            updated_df = pd.concat([ledger_df, new_row], ignore_index=True)
            try:
                conn.update(data=updated_df)
                st.success(f"Successfully added trade entry for {ticker}!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Failed to update Google Sheet: {e}")
