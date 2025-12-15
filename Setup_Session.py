import streamlit as st
from firestore_config import get_all_sessions_ref, get_session_ref
from wallet import generate_key_pair
import uuid
import time
from datetime import datetime
import pandas as pd

# Mandatory imports for the separate web page files
# Ensure firestore_config is loaded and initializes Firebase if needed
if 'db' not in st.session_state:
    try:
        # Attempt to import the config file which runs the initialization logic
        import firestore_config 
    except ImportError:
        st.error("Missing required configuration file: firestore_config.py. Please ensure it is present.")
        st.stop()

# --- UI Customization (Blue/White Theme) ---
st.set_page_config(layout="centered", page_title="Session Setup")
st.markdown("""
    <style>
    /* Styling for the overall theme */
    .big-font { font-size:30px !important; font-weight: bold; color: #1E40AF; border-bottom: 2px solid #60A5FA; padding-bottom: 5px; margin-top: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; padding: 10px 0; background-color: #3B82F6; color: white; font-size: 16px; font-weight: 700; border: none; transition: background-color 0.3s; }
    .stButton>button:hover { background-color: #2563EB; }
    .stCode { background-color: #EBF8FF; border-left: 5px solid #3B82F6; padding: 10px; border-radius: 5px; overflow-x: auto; }
    </style>
    """, unsafe_allow_html=True)

# --- Constants ---
MAX_SESSIONS = 5
MAX_CANDIDATES = 10

st.title("🔑 Voting Session Setup Portal")
st.markdown("<p class='big-font'>Create New Voting Session</p>", unsafe_allow_html=True)

# --- 1. Session Creation Form ---

session_ref = get_all_sessions_ref()
try:
    current_sessions = list(session_ref.stream())
    num_sessions = len(current_sessions)
except Exception as e:
    st.error(f"Error checking session count: {e}")
    num_sessions = 0 # Assume 0 if error

if num_sessions < MAX_SESSIONS:
    st.info(f"You currently have {num_sessions} active sessions (Max {MAX_SESSIONS}).")
    with st.form("new_session_form"):
        session_name = st.text_input("Name of Election Session (e.g., 'Class President 2026')", max_chars=50)
        candidates_text = st.text_area(f"Candidates (One per line, Max {MAX_CANDIDATES})", value="Candidate A\nCandidate B\nCandidate C")
        
        submitted = st.form_submit_button("Generate New Session")

        if submitted:
            # Clean and filter candidate list
            candidates = [c.strip() for c in candidates_text.split('\n') if c.strip()]
            session_id = str(uuid.uuid4()).split('-')[0].upper() # Short unique ID (e.g., FDFD)
            pin = str(uuid.uuid4().int % 10000).zfill(4) # 4-digit PIN for both Host/Auditor

            if not session_name or not candidates:
                st.error("Session Name and Candidate list cannot be empty.")
            elif len(candidates) > MAX_CANDIDATES:
                st.error(f"Maximum {MAX_CANDIDATES} candidates allowed per session.")
            else:
                # Generate unique cryptographic keys for the Host (Proof-of-Authority)
                host_private_key, host_public_key = generate_key_pair()
                
                new_session_data = {
                    'session_id': session_id,
                    'name': session_name,
                    'host_public_key': host_public_key,
                    'host_private_key': host_private_key, # Stored securely on the host side
                    'pin': pin,
                    'candidates': candidates,
                    'status': 'registration_open',
                    'created_at': time.time(),
                    'voter_count': 0
                }

                try:
                    # Save session data to Firestore (Document ID is the session ID)
                    get_session_ref(session_id).set(new_session_data)
                    st.success(f"Session '{session_name}' Created Successfully!")
                    st.session_state.new_session_data = new_session_data
                except Exception as e:
                    st.error(f"Failed to save session to database: {e}")
                
                st.rerun()

else:
    st.warning(f"Maximum of {MAX_SESSIONS} sessions reached. Delete a session below to create a new one.")


# --- 2. Display and Management ---

st.markdown("---")
st.markdown("<p class='big-font'>Active Sessions & Credentials</p>", unsafe_allow_html=True)

if 'new_session_data' in st.session_state:
    st.subheader("Newly Created Session Credentials")
    data = st.session_state.new_session_data
    
    st.code(f"Session Name: {data['name']}")
    st.code(f"Session ID: {data['session_id']}")
    st.code(f"Host PIN (Host/Auditor Access): {data['pin']}")
    
    st.warning("COPY AND SECURELY STORE THESE CRYPTOGRAPHIC CREDENTIALS!")
    st.code(f"Host Public Key: {data['host_public_key']}")
    st.code(f"Host Private Key: {data['host_private_key']}")
    
    st.info(f"""
        To access the portals, use the Session ID and PIN on the respective pages:
        1. **Host Portal:** Control the election status and manage voters.
        2. **Voter Portal:** For registration, voting, and public results.
        3. **Auditor Page:** For auditing, which exposes private keys (USE WITH CAUTION).
    """)
    
    del st.session_state.new_session_data


# Display all existing sessions
if current_sessions:
    st.subheader("All Active Sessions")
    
    # Create a DataFrame for easy display and interaction
    session_data = []
    for doc in current_sessions:
        data = doc.to_dict()
        session_data.append({
            'ID': data['session_id'],
            'Name': data['name'],
            'Status': data['status'].replace('_', ' ').title(),
            'PIN': data['pin'],
            'Voters': data.get('voter_count', 0),
            'Host Key (Start)': data['host_public_key'][:8] + '...'
        })
    
    df = pd.DataFrame(session_data)
    st.dataframe(df, use_container_width=True)

    # Deletion Form
    with st.form("delete_session_form"):
        st.subheader("Delete Session")
        delete_id = st.text_input("Enter Session ID to Delete:").upper()
        delete_pin = st.text_input("Enter Host PIN to Confirm Deletion:", type="password")
        delete_submitted = st.form_submit_button("Delete Session (Irreversible)")

        if delete_submitted:
            doc_to_delete = next((doc for doc in current_sessions if doc.id == delete_id), None)
            if doc_to_delete and doc_to_delete.to_dict().get('pin') == delete_pin:
                try:
                    # Delete the session document
                    doc_to_delete.reference.delete()
                    
                    # NOTE: A robust system would also recursively delete the 
                    # voters and blockchain subcollections here.
                    
                    st.success(f"Session {delete_id} deleted.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting session: {e}")
            else:
                st.error("Invalid Session ID or PIN.")
                
else:
    st.info("No active sessions. Create one above to begin.")
