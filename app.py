import datetime
import json
import os
import gspread
import numpy as np
import pandas as pd
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
INITIAL_CAPITAL = 3000000.00  # ₹30,000,000 Starting NAV
SPREADSHEET_NAME = "ETF_Trading_Ledger"


# --- 2. GOOGLE SHEETS AUTHENTICATION ---
def get_gspread_client():
    creds_json = os.environ.get("GSPREAD_CREDS")
    if creds_json:
        creds_dict = json.loads(creds_json)
    else:
        # Local fallback if testing on machine
        with open("service_account.json") as f:
            creds_dict = json.load(f)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)


# --- 3. CORE STRATEGY & PNL ENGINE ---
def run_daily_cron():
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"[{today_str}] Running Daily 8-ETF Strategy Cron Engine...")

    # Fetch 1 year of historical daily closing prices
    all_tickers = ETF_UNIVERSE + [LIQUID_ETF]
    df_prices = yf.download(all_tickers, period="1y")["Close"]

    if df_prices.empty:
        raise ValueError("Failed to download price data from Yahoo Finance.")

    # Calculate 200-Day Moving Averages
    df_sma200 = df_prices.rolling(window=200).mean()

    latest_prices = df_prices.iloc[-1]
    latest_sma200 = df_sma200.iloc[-1]

    # Evaluate 200-DMA Breaches (Price < 200-SMA by >2%)
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

    # Calculate Portfolio NAV & Allocations
    # (Integrates with initial capital base or reads last known NAV from sheet)
    gc = get_gspread_client()
    sheet = gc.open(SPREADSHEET_NAME).sheet1
    all_records = sheet.get_all_records()

    if len(all_records) > 0:
        last_row = all_records[-1]
        prev_nav = float(last_row.get("Total NAV", INITIAL_CAPITAL))
    else:
        prev_nav = INITIAL_CAPITAL

    # Example Daily NAV return calculation based on active assets
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
        # Move portion of breached ETFs into LIQUIDBEES
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

    # Current month calculation
    current_month = datetime.date.today().month

    # --- 4. APPEND ROW TO GOOGLE SHEETS ---
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
    print(
        f"[{today_str}] Successfully appended entry. Total NAV: ₹{current_nav:,.2f}"
    )


if __name__ == "__main__":
    run_daily_cron()
