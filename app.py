import datetime
import json
import os
import gspread
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURATION & CONSTANTS ---
ETF_UNIVERSE = [
    "NIFTYBEES.NS",
    "JUNIORBEES.NS",
    "MID150BEES.NS",
    "AUTOBEES.NS",
    "ITBEES.NS",
    "PHARMABEES.NS",
    "GOLDBEES.NS",
    "MON100.NS",
]
LIQUID_ETF = "LIQUIDBEES.NS"
INITIAL_CAPITAL = 3000000.00  # ₹3,000,000 Starting NAV
SPREADSHEET_NAME = "ETF_Trading_Ledger"
SHEET_ID = "19j4tv6fttY6CT6TjchrZrx-hFzGxCC3g8bVnZ8zLhNg"


# --- 2. GOOGLE SHEETS AUTHENTICATION ---
def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    # 1. Read from Streamlit Cloud Secrets
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            key = creds_dict["private_key"]
            if "\\n" in key:
                key = key.replace("\\n", "\n")
            creds_dict["private_key"] = key.strip("'\"")

        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, scope
        )
        return gspread.authorize(creds)

    # 2. Read from Environment Variable (GitHub Actions)
    creds_json = os.environ.get("GSPREAD_CREDS")
    if creds_json:
        creds_dict = json.loads(creds_json)
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace(
                "\\n", "\n"
            )
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, scope
        )
        return gspread.authorize(creds)

    # 3. Local fallback
    if os.path.exists("service_account.json"):
        with open("service_account.json") as f:
            creds_dict = json.load(f)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, scope
        )
        return gspread.authorize(creds)

    raise FileNotFoundError("No Google Cloud credentials found.")


# --- 3. CORE STRATEGY & PNL ENGINE ---
def run_daily_cron():
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    # Fetch 1 year of historical daily closing prices
    all_tickers = ETF_UNIVERSE + [LIQUID_ETF]
    df_prices = yf.download(all_tickers, period="1y")["Close"]

    if df_prices.empty:
        st.error("Failed to download price data from Yahoo Finance.")
        return

    # Calculate 200-Day Moving Averages
    df_sma200 = df_prices.rolling(window=200).mean()

    latest_prices = df_prices.iloc[-1]
    latest_sma200 = df_sma200.iloc[-1]

    # Evaluate 200-DMA Breaches
    breached_etfs = []
    healthy_etfs = []

    for etf in ETF_UNIVERSE:
        current_price = latest_prices[etf]
        sma_val = latest_sma200[etf]

        if pd.isna(sma_val):
            healthy_etfs.append(etf)
            continue

        pct_diff = ((current_price - sma_val) / sma_val) * 100

        if pct_diff < -2.0:
            breached_etfs.append(f"{etf.replace('.NS','')}({pct_diff:.1f}%)")
        else:
            healthy_etfs.append(etf)

    # Connect to Google Sheet Ledger
    gc = get_gspread_client()
    sheet = gc.open_by_key(SHEET_ID).sheet1
    all_records = sheet.get_all_records()

    if len(all_records) > 0:
        last_row = all_records[-1]
        prev_nav = float(last_row.get("Total NAV", INITIAL_CAPITAL))
    else:
        prev_nav = INITIAL_CAPITAL

    # Daily NAV return calculation based on active assets
    daily_market_return = (
        df_prices[ETF_UNIVERSE].pct_change().iloc[-1].mean()
    )
    if pd.isna(daily_market_return):
        daily_market_return = 0.0

    current_nav = prev_nav * (1 + daily_market_return)
    daily_pnl = current_nav - prev_nav
    daily_pnl_pct = (daily_pnl / prev_nav) * 100

    # Determine allocation splits based on breached circuit breakers
    if len(breached_etfs) > 0:
        cash_ratio = len(breached_etfs) / len(ETF_UNIVERSE)
        liquidbees_cash = current_nav * cash_ratio
        equities_deployed = current_nav - liquidbees_cash
        execution_note = f"Exit triggered for {', '.join(breached_etfs)}. Capital moved to LIQUIDBEES."
    else:
        equities_deployed = current_nav
        liquidbees_cash = 0.0
        execution_note = (
            "All 8 ETFs holding above 200-DMA threshold. 100% Deployed."
        )

    current_month = datetime.date.today().month

    # Append Row to Google Sheet
    new_ledger_entry = [
        today_str,
        round(current_nav, 2),
        round(daily_pnl, 2),
        f"{daily_pnl_pct:+.2f}%",
        round(equities_deployed, 2),
        round(liquidbees_cash, 2),
        f"Month {current_month}",
        execution_note,
    ]

    sheet.append_row(new_ledger_entry)


# --- 4. STREAMLIT UI DASHBOARD ---
st.set_page_config(
    page_title="8-ETF Paper Trading Terminal", layout="wide"
)

st.title("📊 8-ETF Institutional Paper Trading Terminal")

# Load and Display Google Sheets Ledger
try:
    gc = get_gspread_client()
    sheet = gc.open_by_key(SHEET_ID).sheet1
    records = sheet.get_all_records()
    df_ledger = pd.DataFrame(records)

    if not df_ledger.empty:
        latest = df_ledger.iloc[-1]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total NAV", f"₹{latest.get('Total NAV', 0):,}")
        col2.metric("Daily P&L", f"₹{latest.get('Daily PnL', 0):,}")
        col3.metric(
            "Equities Deployed", f"₹{latest.get('Equities Deployed', 0):,}"
        )
        col4.metric("LIQUIDBEES Cash", f"₹{latest.get('LIQUIDBEES Cash', 0):,}")

        st.divider()
        st.subheader("Execution Ledger")
        st.dataframe(df_ledger, use_container_width=True)
    else:
        st.info("Trading ledger is empty.")
except Exception as e:
    st.error(f"Error loading Google Sheets ledger: {e}")
