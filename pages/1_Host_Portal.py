import streamlit as st
import pandas as pd
from datetime import datetime
import time

# Relative imports
try:
    from firestore_config import get_session_ref, get_voters_collection_ref, get_blockchain_collection_ref
    from blockchain import Blockchain
except ImportError:
    st.error("Missing configuration file. Please run Setup_Session.py first.")
    st.stop()

# --- UI Customization (Blue/White Theme) ---
st.set_page_config(layout="wide", page_title="Host Portal")
st.markdown("""
    <style>
    .big-font { font-size:30px !important; font-weight: bold; color: #1E40AF; border-bottom: 2px solid #60A5FA; padding-bottom: 5px; margin-top: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; padding: 10px 0; background-color: #3B82F6; color: white; font-size: 16px; font-weight: 700; border: none; }
    .stButton>button:hover { background-color: #2563EB; }
    .stCode { background-color: #EBF8FF; border-left: 5px solid #3B82F6; }
    </style>
    """, unsafe_allow_html=True)

# --- State Management and Login ---

if 'host_logged_in' not in st.session_state:
    st.session_state.host_logged_in = False
if 'session_data' not in st.session_state:
    st.session_state.session_data = None
if 'blockchain_instance' not in st.session_state:
    st.session_state.blockchain_instance = None


def fetch_session_data(session_id):
    """Fetches session data and voter data from Firestore."""
    try:
        session_doc = get_session_ref(session_id).get()
        if not session_doc.exists:
            st.error("Session ID not found.")
            return None, None

        session_data = session_doc.to_dict()
        
        # Fetch voters
        voters_docs = get_voters_collection_ref(session_id).stream()
        voter_list = [doc.to_dict() for doc in voters_docs]
        
        return session_data, voter_list
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None, None

def update_session_status(new_status):
    """Updates the voting status in the Firestore session document."""
    if not st.session_state.session_data:
        return
    try:
        session_id = st.session_state.session_data['session_id']
        get_session_ref(session_id).update({'status': new_status})
        st.session_state.session_data['status'] = new_status
        st.success(f"Voting status updated to: {new_status.replace('_', ' ').upper()}")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"Failed to update status: {e}")

# --- LOGIN FORM ---
if not st.session_state.host_logged_in:
    st.header("Host Portal Access")
    with st.form("host_login"):
        session_id = st.text_input("Session ID (e.g., FDFD)", max_chars=4).upper()
        pin = st.text_input("Host PIN", type="password", max_chars=4)
        submitted = st.form_submit_button("Enter Host Portal")

        if submitted:
            session_data, _ = fetch_session_data(session_id)
            
            if session_data and session_data.get('pin') == pin:
                st.session_state.host_logged_in = True
                st.session_state.session_data = session_data
                
                # Initialize Blockchain instance for this session
                bc = Blockchain(
                    session_id=session_data['session_id'],
                    host_public_key=session_data['host_public_key'],
                    host_private_key=session_data['host_private_key']
                )
                st.session_state.blockchain_instance = bc
                st.rerun()
            else:
                st.error("Invalid Session ID or PIN.")
    st.stop()
    
# --- LOGGED IN VIEW ---
session = st.session_state.session_data
bc = st.session_state.blockchain_instance

st.title(f"🗳️ Host Portal: {session['name']}")
st.subheader(f"Session ID: {session['session_id']} | Status: {session['status'].upper().replace('_', ' ')}")

# Fetch the latest data on every rerun
session, voter_list = fetch_session_data(session['session_id'])
if not session or not voter_list:
    # Re-initialize if data load fails, assuming chain keys are the same
    bc = Blockchain(
        session['session_id'], session['host_public_key'], session['host_private_key']
    )
    st.session_state.blockchain_instance = bc
    voter_list = [] # Use empty list if loading failed
    
st.session_state.session_data = session


tab_voters, tab_status, tab_ledger = st.tabs(["Registered Voters", "Status Control & Candidates", "Blockchain Ledger"])

# ==============================================================================
# 1. REGISTERED VOTERS
# ==============================================================================
with tab_voters:
    st.markdown("<p class='big-font'>Current Registered Voters</p>", unsafe_allow_html=True)
    
    if voter_list:
        voters_df = pd.DataFrame(voter_list)
        voters_df['eligible_date'] = pd.to_datetime(voters_df['dob'], errors='coerce').dt.strftime('%Y-%m-%d')
        
        # Displaying only Name, DOB, Public Key, and Vote Status (NO private key here)
        display_df = voters_df[['name', 'eligible_date', 'public_key', 'has_voted', 'is_eligible']]
        display_df.rename(columns={
            'eligible_date': 'Date of Birth',
            'public_key': 'Public Key (ID)',
            'has_voted': 'Voted',
            'is_eligible': 'Eligible (Age 18+)'
        }, inplace=True)
        
        st.dataframe(display_df, use_container_width=True)
        st.info(f"Total Registered Voters: {len(voters_df)} (Max 100)")
        
        # --- Voter Removal (Only Host can remove) ---
        st.markdown("---")
        st.subheader("Remove Voter (Cannot add or change other entries)")
        with st.form("remove_voter"):
            voter_pk_to_remove = st.text_input("Enter Public Key of Voter to Remove:")
            remove_submitted = st.form_submit_button("Remove Voter")
            
            if remove_submitted:
                try:
                    voter_ref = get_voters_collection_ref(session['session_id']).document(voter_pk_to_remove)
                    if voter_ref.get().exists:
                        voter_ref.delete()
                        # Update session voter count 
                        get_session_ref(session['session_id']).update({'voter_count': session.get('voter_count', 1) - 1})
                        st.success(f"Voter with Public Key {voter_pk_to_remove[:8]}... removed.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Voter Public Key not found.")
                except Exception as e:
                    st.error(f"Error removing voter: {e}")
    else:
        st.info("No voters registered yet.")

# ==============================================================================
# 2. STATUS CONTROL & CANDIDATES
# ==============================================================================
with tab_status:
    st.markdown("<p class='big-font'>Election Status and Candidate List</p>", unsafe_allow_html=True)
    
    status = session['status']
    
    # Status Indicators
    col1, col2, col3 = st.columns(3)
    with col1:
        if status == 'registration_open': st.success("Registration is OPEN")
        else: st.warning("Registration is CLOSED")
    with col2:
        if status == 'voting_open': st.success("Voting is OPEN")
        else: st.warning("Voting is CLOSED")
    with col3:
        if status == 'election_ended': st.info("Election Ended")
        else: st.info("Election Active")
        
    st.markdown("---")

    # Status Control Buttons
    st.subheader("Control Voting Period")
    
    colA, colB, colC = st.columns(3)
    with colA:
        if status == 'registration_open':
            if st.button("Start Voting (Close Registration)"):
                update_session_status('voting_open')
        else:
            st.button("Start Voting (Close Registration)", disabled=True)
            
    with colB:
        if status == 'voting_open':
            if st.button("End Voting"):
                update_session_status('election_ended')
        else:
            st.button("End Voting", disabled=True)

    with colC:
        if st.button("Reset Session & Blockchain", help="Deletes all blockchain data and resets all voter 'has_voted' flags."):
            bc.reset_chain()
            voters_ref = get_voters_collection_ref(session['session_id'])
            for doc in voters_ref.stream():
                doc.reference.update({'has_voted': False})
            update_session_status('registration_open')
            st.success("Session reset complete.")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    
    # Candidate List (Read-only on this page, set during setup)
    st.subheader("Candidate List (Fixed from Setup)")
    st.info(f"Max 10 Candidates Allowed. Current Count: {len(session['candidates'])}")
    
    candidates_list = "\n".join(session['candidates'])
    st.code(candidates_list)


# ==============================================================================
# 3. BLOCKCHAIN LEDGER
# ==============================================================================
with tab_ledger:
    st.markdown("<p class='big-font'>Blockchain Ledger (View Only)</p>", unsafe_allow_html=True)
    
    # Re-load chain (ensure latest data)
    bc.load_chain()
    
    if bc.chain:
        for block in reversed(bc.chain):
            with st.expander(f"Block #{block.index} - {datetime.fromtimestamp(block.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"):
                st.json(block.to_dict())
    else:
        st.info("Blockchain is empty (Genesis block not yet written or loaded).")
