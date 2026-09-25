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

st_autorefresh(interval=60000, key="price_feed_refresh")

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

conn = st.connection("gsheets", type=GSheetsConnection)

def get_ledger_data():
    try:
        df = conn.read(ttl=2)
        if df is None or df.empty:
            return pd.DataFrame(columns=EXPECTED_COLUMNS)
        
        df.columns = [str(c).strip() for c in df.columns]
        
        rename_map = {}
        for col in df.columns:
            c_clean = col.upper().replace("_", " ").replace("-", " ")
            if c_clean in ["PRICE", "BUY PRICE", "BUYPRICE"]:
                rename_map[col] = "Buy_Price"
            elif c_clean in ["AMOUNT", "TOTAL AMOUNT", "TOTALAMOUNT", "VALUE"]:
                rename_map[col] = "Total_Amount"
            elif c_clean in ["SYMBOL", "TICKER", "ETF"]:
                rename_map[col] = "Ticker"
            elif c_clean in ["ACTION", "TYPE", "TRADE TYPE"]:
                rename_map[col] = "Type"
            elif c_clean in ["DATE"]:
                rename_map[col] = "Date"
            elif c_clean in ["QUANTITY", "QTY", "UNITS"]:
                rename_map[col] = "Quantity"

        df = df.rename(columns=rename_map)
        
        for col in EXPECTED_COLUMNS:
            if col not in df.columns:
                df[col] = None
                
        return df[EXPECTED_COLUMNS].dropna(subset=["Ticker", "Type"], how="any")
    except Exception as e:
        st.error(f"Error reading Google Sheet ledger: {e}")
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

ledger_df = get_ledger_data()

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

if not holdings.empty:
    holdings["Live_Price"] = holdings["Ticker"].map(lambda x: live_data.get(x, {}).get("live_price", 0.0))
    holdings["Prev_Close"] = holdings["Ticker"].map(lambda x: live_data.get(x, {}).get("prev_close", 0.0))
    holdings["Current_Value"] = holdings["Quantity"] * holdings["Live_Price"]
    holdings["Daily_PnL"] = holdings["Quantity"] * (holdings["Live_Price"] - holdings["Prev_Close"])
    holdings["Total_PnL"] = holdings["Current_Value"] - holdings["Total_Amount"]
else:
    holdings = pd.DataFrame(columns=["Ticker", "Quantity", "Total_Amount", "Live_Price", "Prev_Close", "Current_Value", "Daily_PnL", "Total_PnL"])

equity_holdings = holdings[holdings["Ticker"] != "LIQUIDCASE.NS"]
equity_cost = equity_holdings["Total_Amount"].sum() if not equity_holdings.empty else 0.0

lc_row = holdings[holdings["Ticker"] == "LIQUIDCASE.NS"]
lc_current_value = lc_row["Current_Value"].sum() if not lc_row.empty else 0.0
lc_units = lc_row["Quantity"].sum() if not lc_row.empty else 0.0

total_portfolio_value = holdings["Current_Value"].sum() if not holdings.empty else 0.0
daily_pnl = holdings["Daily_PnL"].sum() if not holdings.empty else 0.0
total_pl = holdings["Total_PnL"].sum() if not holdings.empty else 0.0

st.title("8-ETF Institutional Paper Trading Terminal")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total NAV", f"₹{total_portfolio_value:,.2f}")
col2.metric("Daily P&L", f"₹{daily_pnl:,.2f}", delta=f"{daily_pnl:,.2f}")
col3.metric("Total P&L", f"₹{total_pl:,.2f}", delta=f"{total_pl:,.2f}")
col4.metric("Equities Deployed", f"₹{equity_cost:,.2f}")
col5.metric("LIQUIDCASE Value", f"₹{lc_current_value:,.2f}", delta=f"{int(lc_units)} Units")

st.markdown("---")

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
    if not ledger_df.empty:
        st.dataframe(ledger_df, use_container_width=True)
    else:
        st.warning("No ledger entries found in Google Sheet.")

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
