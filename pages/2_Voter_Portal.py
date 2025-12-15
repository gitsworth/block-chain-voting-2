import streamlit as st
import pandas as pd
from datetime import datetime, date
import time

# Relative imports
try:
    from firestore_config import get_session_ref, get_voters_collection_ref
    from wallet import generate_key_pair, sign_transaction, verify_signature
    from blockchain import Blockchain
except ImportError:
    st.error("Missing configuration file. Please run Setup_Session.py first.")
    st.stop()


# --- UI Customization (Blue/White Theme) ---
st.set_page_config(layout="wide", page_title="Voter Portal")
st.markdown("""
    <style>
    .big-font { font-size:30px !important; font-weight: bold; color: #1E40AF; border-bottom: 2px solid #60A5FA; padding-bottom: 5px; margin-top: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; padding: 10px 0; background-color: #3B82F6; color: white; font-size: 16px; font-weight: 700; border: none; }
    .stButton>button:hover { background-color: #2563EB; }
    .stCode { background-color: #EBF8FF; border-left: 5px solid #3B82F6; }
    </style>
    """, unsafe_allow_html=True)

# --- State Management and Login ---

if 'voter_session_data' not in st.session_state:
    st.session_state.voter_session_data = None
if 'voter_blockchain_instance' not in st.session_state:
    st.session_state.voter_blockchain_instance = None


def calculate_age(dob):
    """Calculates age in years from date of birth."""
    today = date.today()
    # Subtract 1 if the birthday hasn't occurred yet this year
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def get_session_and_voters(session_id):
    """Fetches session data and voter list."""
    try:
        session_doc = get_session_ref(session_id).get()
        if not session_doc.exists:
            return None, None
        
        # Fetch only the public keys and names for registration check speed
        voters_docs = get_voters_collection_ref(session_id).stream()
        voter_list = [doc.to_dict() for doc in voters_docs]
        
        return session_doc.to_dict(), voter_list
    except Exception as e:
        st.error(f"Error fetching session data: {e}")
        return None, None

def get_total_votes(chain, candidates):
    """Tallies votes from the blockchain."""
    results = {name: 0 for name in candidates}
    voted_voters = set()
    
    for block in chain[1:]:
        for tx in block.transactions:
            voter_id = tx.get('voter_id')
            vote_candidate = tx.get('candidate')
            
            # Simple double-spend check on chain (in case voter table failed)
            if voter_id and voter_id not in voted_voters and vote_candidate in results:
                results[vote_candidate] += 1
                voted_voters.add(voter_id)
                
    return results, len(voted_voters)


# --- LOGIN / SESSION SELECTION ---
# Check query params for session ID (allows URL access)
session_id_query = st.experimental_get_query_params().get('session_id', [''])[0].upper()
if session_id_query and not st.session_state.voter_session_data:
    session_data, _ = get_session_and_voters(session_id_query)
    if session_data:
        st.session_state.voter_session_data = session_data
        # Initialize BC instance (keys only needed for actual block creation, but we need the instance)
        st.session_state.voter_blockchain_instance = Blockchain(
            session_id=session_data['session_id'],
            host_public_key=session_data['host_public_key'],
            host_private_key=session_data['host_private_key']
        )
        st.experimental_set_query_params(session_id=session_id_query)
        st.rerun()
    # Note: If invalid ID, let the form below handle it.


if not st.session_state.voter_session_data:
    st.header("Voter Portal Access")
    st.info("Enter the Session ID provided by the Host.")
    with st.form("voter_session_select"):
        session_id = st.text_input("Enter Session ID:", max_chars=4).upper()
        submitted = st.form_submit_button("Access Session")
        
        if submitted:
            session_data, _ = get_session_and_voters(session_id)
            if session_data:
                st.experimental_set_query_params(session_id=session_id)
                st.rerun()
            else:
                st.error("Invalid Session ID.")
    st.stop()

# --- LOGGED IN VIEW ---
session = st.session_state.voter_session_data
bc = st.session_state.voter_blockchain_instance

st.title(f"🗳️ Voter Portal: {session['name']}")
st.subheader(f"Session ID: {session['session_id']} | Status: {session['status'].upper().replace('_', ' ')}")

# Re-fetch data for live updates
session, voter_list = get_session_and_voters(session['session_id'])
if not session or voter_list is None:
    st.error("Critical session data missing.")
    st.stop()
st.session_state.voter_session_data = session


tab_register, tab_vote, tab_results, tab_ledger = st.tabs(["Register", "Cast Vote", "Results", "Blockchain Ledger"])


# ==============================================================================
# 1. REGISTRATION
# ==============================================================================
with tab_register:
    st.markdown("<p class='big-font'>Voter Registration</p>", unsafe_allow_html=True)
    
    if session['status'] == 'registration_open' and session.get('voter_count', 0) < 100:
        with st.form("voter_registration"):
            new_name = st.text_input("Full Name (Case does not matter)")
            
            # Date of Birth selector (1/1/1900 to Today)
            min_date = date(1900, 1, 1)
            today = date.today()
            dob = st.date_input("Date of Birth", min_value=min_date, max_value=today, value=date(2000, 1, 1))

            voter_pin = st.text_input("Create Voter Access PIN (4 digits)", type="password", max_chars=4)

            submitted = st.form_submit_button("Register and Get Keys")
            
            if submitted:
                if not new_name or len(voter_pin) != 4 or not voter_pin.isdigit():
                    st.error("Please enter a name and a valid 4-digit PIN.")
                    st.stop()

                age = calculate_age(dob)
                
                if age < 18:
                    st.error(f"Not eligible. Age is {age}. Must be 18 or older.")
                else:
                    # Check if voter name is already registered (case-insensitive)
                    existing_names = {v['name'].lower() for v in voter_list}
                    if new_name.strip().lower() in existing_names:
                        st.warning("A voter with this name is already registered.")
                    else:
                        # 1. Generate Keys
                        private_key, public_key = generate_key_pair()
                        
                        # 2. Prepare Data for Firestore
                        voter_data = {
                            'name': new_name.strip(),
                            'dob': dob.strftime('%Y-%m-%d'),
                            'age': age,
                            'public_key': public_key,
                            'private_key': private_key, # Storing private key
                            'has_voted': False,
                            'is_eligible': True,
                            'registration_pin': voter_pin,
                            'registered_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        try:
                            # 3. Save to Firestore (Public Key as Document ID)
                            voters_ref = get_voters_collection_ref(session['session_id'])
                            voters_ref.document(public_key).set(voter_data)
                            
                            # 4. Increment voter count in session document
                            get_session_ref(session['session_id']).update({'voter_count': session.get('voter_count', 0) + 1})
                            
                            st.success(f"Registration successful for {new_name} (Age {age}).")
                            st.subheader("⚠️ YOUR CRYPTOGRAPHIC CREDENTIALS ⚠️")
                            st.warning("You must copy and save these keys now. They are your sole means of voting!")
                            
                            st.code(f"Voter ID (Public Key): {public_key}")
                            st.code(f"Secret Wallet Key (Private Key): {private_key}")
                            
                            st.info("You can now go to the 'Cast Vote' tab.")
                            time.sleep(1)
                            st.rerun() # Refresh to update list/status
                            
                        except Exception as e:
                            st.error(f"Database error during registration: {e}")
                
    elif session['status'] != 'registration_open':
        st.info("Registration is currently closed.")
    elif session.get('voter_count', 0) >= 100:
        st.error("Maximum voter limit (100) reached for this session.")
    else:
        st.info("Check session status.")


# ==============================================================================
# 2. CAST VOTE
# ==============================================================================
with tab_vote:
    st.markdown("<p class='big-font'>Cast Your Vote</p>", unsafe_allow_html=True)
    
    if session['status'] == 'voting_open':
        with st.form("vote_casting"):
            st.subheader("Identity Verification")
            # Voter uses the generated keys
            voter_id = st.text_input("Voter ID (Public Key)")
            secret_key = st.text_input("Secret Wallet Key (Private Key)", type="password")
            
            st.subheader("Ballot")
            candidate = st.selectbox("Select Candidate:", session['candidates'])
            
            cast_vote_button = st.form_submit_button("Cast Vote Securely")
            
            if cast_vote_button:
                if not voter_id or not secret_key:
                    st.error("Please fill in all identity fields.")
                    st.stop()
                
                try:
                    voter_doc = get_voters_collection_ref(session['session_id']).document(voter_id).get()
                    
                    if not voter_doc.exists:
                        st.error("Invalid Voter ID (Public Key).")
                        st.stop()
                        
                    voter_info = voter_doc.to_dict()
                    
                    if not voter_info.get('is_eligible'):
                        st.error("Voter is not eligible (age requirement not met).")
                    elif voter_info.get('has_voted'):
                        st.warning("You have already cast your vote.")
                    elif voter_info['private_key'] != secret_key:
                        st.error("Invalid Secret Wallet Key.")
                    else:
                        # --- 1. Signing Transaction ---
                        bc_instance = st.session_state.voter_blockchain_instance
                        
                        data_to_sign = f"VOTE|{voter_id}|{candidate}|{datetime.now().isoformat()}"
                        signature = sign_transaction(secret_key, data_to_sign)
                        
                        # --- 2. Verification and Chain Recording ---
                        if signature and verify_signature(voter_id, data_to_sign, signature):
                            
                            bc_instance.new_transaction(voter_id, candidate, f"Vote for {candidate}")
                            bc_instance.new_block() # Mine and save the block to Firestore
                            
                            # --- 3. Update Voter Status in DB ---
                            get_voters_collection_ref(session['session_id']).document(voter_id).update({'has_voted': True})
                            
                            st.success(f"Vote cast for **{candidate}**! Thank you.")
                            st.info("The blockchain has been updated. Check the 'Blockchain Ledger' tab.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Cryptographic verification failed. Vote rejected.")
                            
                except Exception as e:
                    st.error(f"An error occurred during voting: {e}")
                    
    elif session['status'] == 'registration_open':
        st.info("Voting has not started yet. Please register first, then wait for the Host to open voting.")
    else:
        st.info("Voting is currently closed.")


# ==============================================================================
# 3. RESULTS (Visible to Voter)
# ==============================================================================
with tab_results:
    st.markdown("<p class='big-font'>Live Election Results</p>", unsafe_allow_html=True)
    
    bc.load_chain()
    results, total_voters = get_total_votes(bc.chain, session['candidates'])
    total_votes = sum(results.values())

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.metric("Total Votes Counted", total_votes)
    with col_r2:
        st.metric("Total Registered Voters", session.get('voter_count', 0))

    if total_votes > 0:
        results_df = pd.DataFrame(list(results.items()), columns=['Candidate', 'Votes'])
        st.bar_chart(results_df.set_index('Candidate'))
        st.dataframe(results_df, use_container_width=True)
    else:
        st.info("No votes have been cast yet.")


# ==============================================================================
# 4. BLOCKCHAIN LEDGER (Visible to Voter)
# ==============================================================================
with tab_ledger:
    st.markdown("<p class='big-font'>Public Blockchain Ledger</p>", unsafe_allow_html=True)
    
    bc.load_chain()
    
    if bc.chain:
        st.info(f"Chain Length: {len(bc.chain)} blocks.")
        for block in reversed(bc.chain):
            with st.expander(f"Block #{block.index} - {datetime.fromtimestamp(block.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"):
                # IMPORTANT: Only show public data in this view
                block_data = block.to_dict()
                st.json(block_data)
    else:
        st.info("Blockchain is empty.")
