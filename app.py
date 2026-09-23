import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(layout="wide", page_title="8-ETF Paper Trading Terminal")

st.title("📊 8-ETF Institutional Paper Trading Terminal")

# Initialize GSheets connection
conn = st.connection("gsheets", type=GSheetsConnection)

# Load data automatically from Google Sheet or fallback
try:
    df_sheet = conn.read(ttl="1m")
    if "ledger_df" not in st.session_state:
        st.session_state.ledger_df = df_sheet
except Exception:
    if "ledger_df" not in st.session_state:
        st.session_state.ledger_df = pd.DataFrame([
            {
                "Date": "2026-09-23",
                "Total NAV": 3000000,
                "Daily PnL": 0,
                "Daily Return (%)": "+0.00%",
                "Equities Deployed": 3000000,
                "LIQUIDCASE Cash": 0,
                "Strategy Period": "Week 1",
                "Execution Notes": "Initial setup"
            }
        ])

# Compute Dynamic Totals
latest_row = st.session_state.ledger_df.iloc[-1]
equities_val = float(latest_row.get("Equities Deployed", 3000000))
cash_val = float(latest_row.get("LIQUIDCASE Cash", 0))

if "liquidcase_cash" not in st.session_state:
    st.session_state.liquidcase_cash = cash_val

if "equities_deployed" not in st.session_state:
    st.session_state.equities_deployed = equities_val

# KPI Metrics
latest_nav = st.session_state.equities_deployed + st.session_state.liquidcase_cash
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total NAV", f"₹{latest_nav:,.0f}")
col2.metric("Daily P&L", "₹0")
col3.metric("Equities Deployed", f"₹{st.session_state.equities_deployed:,.0f}")
col4.metric("LIQUIDCASE Cash", f"₹{st.session_state.liquidcase_cash:,.0f}")

st.markdown("---")

# Navigation Tabs
tab_ledger, tab_park_cash, tab_sip, tab_etfs = st.tabs([
    "📋 Execution Ledger", 
    "🅿️ Park Cash (LIQUIDCASE)", 
    "💸 Deploy Weekly SIP", 
    "📈 My ETF List"
])

# TAB 1: Execution Ledger
with tab_ledger:
    st.subheader("Execution Ledger")
    st.data_editor(
        st.session_state.ledger_df,
        column_config={
            "Total NAV": st.column_config.NumberColumn(format="₹%d"),
            "Daily PnL": st.column_config.NumberColumn(format="₹%d"),
            "Equities Deployed": st.column_config.NumberColumn(format="₹%d"),
            "LIQUIDCASE Cash": st.column_config.NumberColumn(format="₹%d"),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
    )

# TAB 2: Park Cash
with tab_park_cash:
    st.subheader("Park Cash in Zerodha LIQUIDCASE ETF")
    with st.form("park_cash_form"):
        park_amount = st.number_input("Amount to Park (₹)", min_value=1000.0, step=5000.0, value=50000.0)
        park_notes = st.text_input("Execution Notes", value="Manual parking into LIQUIDCASE")
        submit_park = st.form_submit_button("Park Funds")

        if submit_park:
            st.session_state.liquidcase_cash += park_amount
            new_row = {
                "Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "Total NAV": st.session_state.equities_deployed + st.session_state.liquidcase_cash,
                "Daily PnL": 0,
                "Daily Return (%)": "0.00%",
                "Equities Deployed": st.session_state.equities_deployed,
                "LIQUIDCASE Cash": st.session_state.liquidcase_cash,
                "Strategy Period": "Manual Cash Allocation",
                "Execution Notes": f"Parked ₹{park_amount:,.0f} | {park_notes}"
            }
            st.session_state.ledger_df = pd.concat([st.session_state.ledger_df, pd.DataFrame([new_row])], ignore_index=True)
            try:
                conn.update(data=st.session_state.ledger_df)
            except Exception:
                pass
            st.success("Successfully parked funds!")
            st.rerun()

# TAB 3: Deploy Weekly SIP (Updated with your exact 8 ETFs)
with tab_sip:
    st.subheader("Deploy Weekly SIP Funds")
    with st.form("sip_form"):
        sip_amount = st.number_input("Weekly SIP Amount (₹)", min_value=1000.0, step=5000.0, value=25000.0)
        sip_week = st.selectbox("SIP Week / Period", [f"Week {i}" for i in range(1, 53)])
        
        target_etf = st.selectbox("Target ETF Allocation", [
            "MOM30IETF.NS (Nifty200 Momentum 30)",
            "MID150BEES.NS (Nifty Midcap 150)",
            "JUNIORBEES.NS (Nifty Next 50)",
            "MON100.NS (Nasdaq 100 Tech)",
            "AUTOBEES.NS (Nifty Auto & Mobility)",
            "INFRAIETF.NS (Nifty Infrastructure)",
            "GOLDBEES.NS (Physical Gold)",
            "SILVERBEES.NS (Physical Silver)"
        ])
        sip_notes = st.text_input("Execution Notes", value="Weekly SIP Deployment")
        submit_sip = st.form_submit_button("Deploy Weekly SIP")

        if submit_sip:
            st.session_state.equities_deployed += sip_amount
            new_row = {
                "Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "Total NAV": st.session_state.equities_deployed + st.session_state.liquidcase_cash,
                "Daily PnL": 0,
                "Daily Return (%)": "0.00%",
                "Equities Deployed": st.session_state.equities_deployed,
                "LIQUIDCASE Cash": st.session_state.liquidcase_cash,
                "Strategy Period": sip_week,
                "Execution Notes": f"Weekly SIP Deployed ₹{sip_amount:,.0f} into {target_etf} | {sip_notes}"
            }
            st.session_state.ledger_df = pd.concat([st.session_state.ledger_df, pd.DataFrame([new_row])], ignore_index=True)
            try:
                conn.update(data=st.session_state.ledger_df)
            except Exception:
                pass
            st.success("Successfully deployed Weekly SIP!")
            st.rerun()

# TAB 4: My ETF List (Updated with your exact 8-ETF strategy)
with tab_etfs:
    st.subheader("Institutional 8-ETF Watchlist & Allocation Matrix")
    etf_data = pd.DataFrame([
        {"Ticker Symbol": "MOM30IETF.NS", "Index / Asset": "Nifty200 Momentum 30", "Strategy Category": "Factor Alpha"},
        {"Ticker Symbol": "MID150BEES.NS", "Index / Asset": "Nifty Midcap 150", "Strategy Category": "Core Midcap"},
        {"Ticker Symbol": "JUNIORBEES.NS", "Index / Asset": "Nifty Next 50", "Strategy Category": "Next Bluechips"},
        {"Ticker Symbol": "MON100.NS", "Index / Asset": "Nasdaq 100 Tech", "Strategy Category": "Global Tech / USD"},
        {"Ticker Symbol": "AUTOBEES.NS", "Index / Asset": "Nifty Auto & Mobility", "Strategy Category": "EV / Mobility"},
        {"Ticker Symbol": "INFRAIETF.NS", "Index / Asset": "Nifty Infrastructure", "Strategy Category": "National Capex"},
        {"Ticker Symbol": "GOLDBEES.NS", "Index / Asset": "Physical Gold", "Strategy Category": "Sovereign Ballast"},
        {"Ticker Symbol": "SILVERBEES.NS", "Index / Asset": "Physical Silver", "Strategy Category": "Industrial Metal"},
        {"Ticker Symbol": "LIQUIDCASE.NS", "Index / Asset": "Nifty 1D Rate Index", "Strategy Category": "Cash Yield Reserve"}
    ])
    st.dataframe(etf_data, use_container_width=True, hide_index=True)
