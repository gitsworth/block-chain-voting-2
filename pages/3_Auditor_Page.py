import streamlit as st
import pandas as pd
import time

# Relative imports
try:
    from firestore_config import get_session_ref, get_voters_collection_ref
except ImportError:
    st.error("Missing configuration file. Please run Setup_Session.py first.")
    st.stop()

# --- UI Customization (Red/White Theme for Security Warning) ---
st.set_page_config(layout="wide", page_title="Private Auditor Portal")
st.markdown("""
    <style>
    .big-font { font-size:30px !important; font-weight: bold; color: #DC2626; border-bottom: 2px solid #F87171; padding-bottom: 5px; margin-top: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; padding: 10px 0; background-color: #EF4444; color: white; font-size: 16px; font-weight: 700; border: none; }
    .stButton>button:hover { background-color: #DC2626; }
    .stCode { background-color: #FEE2E2; border-left: 5px solid #EF4444; }
    </style>
    """, unsafe_allow_html=True)

# --- State Management and Login ---

if 'auditor_logged_in' not in st.session_state:
    st.session_state.auditor_logged_in = False
if 'auditor_session_data' not in st.session_state:
    st.session_state.auditor_session_data = None


def fetch_session_and_voters(session_id):
    """Fetches session data and voter data from Firestore."""
    try:
        session_doc = get_session_ref(session_id).get()
        if not session_doc.exists:
            return None, None

        session_data = session_doc.to_dict()
        
        # Fetch ALL voter data (including private keys)
        voters_docs = get_voters_collection_ref(session_id).stream()
        voter_list = [doc.to_dict() for doc in voters_docs]
        
        return session_data, voter_list
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None, None

# --- LOGIN FORM ---
if not st.session_state.auditor_logged_in:
    st.header("PRIVATE Auditor Portal Access")
    st.warning("⚠️ This view exposes private keys and should only be used for testing and auditing.")
    with st.form("auditor_login"):
        session_id = st.text_input("Session ID", max_chars=4).upper()
        # Uses the same PIN as the Host
        pin = st.text_input("Host PIN", type="password", max_chars=4) 
        submitted = st.form_submit_button("Enter Auditor Portal")

        if submitted:
            session_data, _ = fetch_session_and_voters(session_id)
            
            if session_data and session_data.get('pin') == pin:
                st.session_state.auditor_logged_in = True
                st.session_state.auditor_session_data = session_data
                st.rerun()
            else:
                st.error("Invalid Session ID or PIN.")
    st.stop()
    
# --- LOGGED IN VIEW ---
session = st.session_state.auditor_session_data

st.title(f"🚨 Private Auditor Portal: {session['name']}")
st.subheader(f"Session ID: {session['session_id']}")
st.error("DATABASE DUMP: This table contains all voter private keys.")

# Fetch the latest data on every rerun
session, voter_list = fetch_session_and_voters(session['session_id'])
if not session or not voter_list:
    st.error("Critical session data missing.")
    st.stop()
st.session_state.auditor_session_data = session


if voter_list:
    voters_df = pd.DataFrame(voter_list)
    voters_df['eligible_date'] = pd.to_datetime(voters_df['dob'], errors='coerce').dt.strftime('%Y-%m-%d')
    
    # Displaying ALL keys, including PRIVATE_KEY
    display_df = voters_df[['name', 'eligible_date', 'public_key', 'private_key', 'has_voted', 'is_eligible']]
    display_df.rename(columns={
        'eligible_date': 'DOB',
        'public_key': 'Voter Public Key (ID)',
        'private_key': 'Voter Private Key (Secret)', # The key column
        'has_voted': 'Voted',
        'is_eligible': 'Eligible'
    }, inplace=True)
    
    st.dataframe(display_df, use_container_width=True)
    st.info(f"Total Registered Voters: {len(voters_df)}")
else:
    st.info("No voters registered yet in this session.")
