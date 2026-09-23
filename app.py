import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(layout="wide", page_title="8-ETF Paper Trading Terminal")

st.title("📊 8-ETF Institutional Paper Trading Terminal")

# ==========================================
# 1. GOOGLE SHEETS CONNECTION & DATA SETUP
# ==========================================
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_sheet = conn.read(ttl="1m")
except Exception:
    conn = None
    df_sheet = None

# Default setup matching your portfolio structure
if "ledger_df" not in st.session_state:
    if df_sheet is not None and not df_sheet.empty:
        st.session_state.ledger_df = df_sheet
    else:
        st.session_state.ledger_df = pd.DataFrame([
            {
                "Date": "2026-09-23",
                "Total NAV": 3000000,
                "Daily PnL": 0,
                "Daily Return (%)": "0.00%",
                "Equities Deployed": 3000000,
                "LIQUIDCASE Cash": 0,
                "Strategy Period": "Initial Setup",
                "Execution Notes": "Base Allocation"
            }
        ])

# Fetch values directly from the latest state row
latest_row = st.session_state.ledger_df.iloc[-1]
equities_val = float(latest_row.get("Equities Deployed", 3000000))
cash_val = float(latest_row.get("LIQUIDCASE Cash", 0))
total_nav = float(latest_row.get("Total NAV", equities_val + cash_val))

# ==========================================
# 2. TOP METRICS BANNER
# ==========================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total NAV", f"₹{total_nav:,.0f}")
col2.metric("Daily P&L", f"₹{float(latest_row.get('Daily PnL', 0)):,.0f}")
col3.metric("Equities Deployed", f"₹{equities_val:,.0f}")
col4.metric("LIQUIDCASE Cash", f"₹{cash_val:,.0f}")

st.markdown("---")

# Navigation Tabs
tab_ledger, tab_park_cash, tab_sip, tab_etfs = st.tabs([
    "📋 Execution Ledger", 
    "🅿️ Park / Add Cash", 
    "💸 Deploy Weekly SIP", 
    "📈 My ETF List"
])

# ==========================================
# TAB 1: EXECUTION LEDGER
# ==========================================
with tab_ledger:
    st.subheader("Execution Ledger")
    
    edited_df = st.data_editor(
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
        key="ledger_editor"
    )
    
    if st.button("💾 Save Ledger Edits"):
        st.session_state.ledger_df = edited_df
        if conn:
            try:
                conn.update(data=edited_df)
                st.success("Ledger successfully saved to Google Sheets!")
            except Exception as e:
                st.error(f"Could not update Google Sheet: {e}")

# ==========================================
# TAB 2: PARK / ADD CASH
# ==========================================
with tab_park_cash:
    st.subheader("Manage Cash Reserves (LIQUIDCASE)")
    
    action_type = st.radio("Action Type", ["Deposit Fresh Capital (Increases NAV)", "Transfer from Equities to Cash Reserve"], horizontal=True)
    
    with st.form("cash_form", clear_on_submit=True):
        amount = st.number_input("Amount (₹)", min_value=1000.0, step=5000.0, value=50000.0)
        notes = st.text_input("Execution Notes", value="Cash Adjustment")
        submit_cash = st.form_submit_button("Execute Cash Allocation")

        if submit_cash:
            if "Deposit Fresh Capital" in action_type:
                new_cash = cash_val + amount
                new_equities = equities_val
                new_nav = total_nav + amount
                note_str = f"Fresh Capital Deposited ₹{amount:,.0f} | {notes}"
            else:
                new_cash = cash_val + amount
                new_equities = max(0.0, equities_val - amount)
                new_nav = total_nav
                note_str = f"Reallocated ₹{amount:,.0f} from Equities to LIQUIDCASE | {notes}"

            new_row = pd.DataFrame([{
                "Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "Total NAV": new_nav,
                "Daily PnL": 0,
                "Daily Return (%)": "0.00%",
                "Equities Deployed": new_equities,
                "LIQUIDCASE Cash": new_cash,
                "Strategy Period": "Cash Allocation",
                "Execution Notes": note_str
            }])
            
            st.session_state.ledger_df = pd.concat([st.session_state.ledger_df, new_row], ignore_index=True)
            
            if conn:
                try:
                    conn.update(data=st.session_state.ledger_df)
                except Exception:
                    pass
            st.success("Cash reserve updated!")
            st.rerun()

# ==========================================
# TAB 3: DEPLOY WEEKLY SIP
# ==========================================
with tab_sip:
    st.subheader("Deploy Weekly SIP Funds")
    
    with st.form("sip_form", clear_on_submit=True):
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
        
        fund_source = st.radio("Funding Source", ["Deduct from LIQUIDCASE Cash", "Add Direct Fresh Capital"], horizontal=True)
        sip_notes = st.text_input("Execution Notes", value="Weekly SIP Deployment")
        submit_sip = st.form_submit_button("Deploy Weekly SIP")

        if submit_sip:
            new_equities = equities_val + sip_amount
            
            if "Deduct from LIQUIDCASE Cash" in fund_source:
                new_cash = cash_val - sip_amount
                new_nav = total_nav  # NAV remains identical, just reallocated
            else:
                new_cash = cash_val
                new_nav = total_nav + sip_amount # Fresh capital increases NAV
            
            new_row = pd.DataFrame([{
                "Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "Total NAV": new_nav,
                "Daily PnL": 0,
                "Daily Return (%)": "0.00%",
                "Equities Deployed": new_equities,
                "LIQUIDCASE Cash": new_cash,
                "Strategy Period": sip_week,
                "Execution Notes": f"SIP Deployed ₹{sip_amount:,.0f} into {target_etf} | {sip_notes}"
            }])
            
            st.session_state.ledger_df = pd.concat([st.session_state.ledger_df, new_row], ignore_index=True)
            
            if conn:
                try:
                    conn.update(data=st.session_state.ledger_df)
                except Exception:
                    pass
            st.success(f"Deployed ₹{sip_amount:,.0f} into {target_etf}!")
            st.rerun()

# ==========================================
# TAB 4: MY EXACT 8-ETF LIST
# ==========================================
with tab_etfs:
    st.subheader("Institutional 8-ETF Watchlist & Strategy Matrix")
    
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
