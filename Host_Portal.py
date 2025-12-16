# Host_Portal.py - The Main App Entry Point (Host & Setup Portal)
import streamlit as st
import pandas as pd
import random
import string
import time
from datetime import datetime
from firestore_config import db, get_session_ref, get_voters_collection_ref, get_blockchain_collection_ref, SINGLE_SESSION_ID
from blockchain import Blockchain
from wallet import generate_key_pair, get_pii_id, hash_data, calculate_age
from google.cloud.firestore_v1 import Increment
from blockchain import Block # Import Block for the audit view

st.set_page_config(
    page_title="Host & Setup Portal",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛡️ Host Authority & Setup Portal")
st.markdown(f"### Management for Active Election: `{SINGLE_SESSION_ID}`")

# --- State Management ---
if 'host_private_key_input' not in st.session_state: st.session_state.host_private_key_input = ""
if 'host_pin_input' not in st.session_state: st.session_state.host_pin_input = ""
if 'auth_successful' not in st.session_state: st.session_state.auth_successful = False

# --- Core Functions ---

@st.cache_data(ttl=1) # 1-second TTL for near-live status
def load_session_data():
    """Loads the single session document and returns data or None. (1s TTL for near-live status)"""
    try:
        doc = get_session_ref().get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        # In a real app, this should handle specific Firebase permissions errors.
        st.error(f"Error loading session data: {e}. Check service account configuration.")
        return None

@st.cache_data(ttl=1) # 1-second TTL for live update
def load_chain_data(session_id):
    """Loads the entire blockchain chain data, sorted by index. (1s TTL for live update)"""
    try:
        # Load all documents from the blockchain collection
        blockchain_ref = get_blockchain_collection_ref(session_id)
        blocks = [doc.to_dict() for doc in blockchain_ref.stream()]
        
        # Ensure the blocks are sorted chronologically by their index
        blocks.sort(key=lambda x: x['index'])
        return blocks
    except Exception as e:
        st.error(f"Error loading blockchain data: {e}")
        return []

def create_new_session(election_name, candidates_list):
    """Creates the single active session and stores host keys."""
    
    host_private_key, host_public_key = generate_key_pair()
    host_pin = ''.join(random.choices(string.digits, k=6))
    
    session_data = {
        'session_id': SINGLE_SESSION_ID,
        'election_name': election_name,
        'candidates': candidates_list,
        'host_public_key': host_public_key,
        'host_pin': host_pin,
        'status': 'registration_open',  # Start directly in registration_open
        'voter_count': 0,
        'total_votes': 0,
        'pending_transactions': 0,
        'pending_transactions_list': [],
        'created_at': time.time()
    }
    
    st.session_state['host_private_key'] = host_private_key
    st.session_state['session_data'] = session_data

    try:
        get_session_ref().set(session_data)
        
        # Initialize blockchain (creates genesis block)
        blockchain_manager = Blockchain(SINGLE_SESSION_ID, host_public_key, host_private_key)
        blockchain_manager.initialize_blockchain()
        
        st.session_state['new_session_created'] = True
        st.rerun()
        
    except Exception as e:
        st.error(f"Failed to create session in Firestore: {e}")

def authenticate_host(pin, private_key, session_data):
    """Authenticates the host against the PIN and stores the private key."""
    
    if pin != session_data.get('host_pin'):
        st.error("Authentication Failed: Invalid Host PIN.")
        return False
        
    st.session_state.host_private_key = private_key
    st.session_state.auth_successful = True
    st.toast("Host Authority Access Granted!")
    st.rerun()

def update_session_status(current_status, new_status):
    """Updates the status of the single active session with guardrails."""
    
    # Validation logic for status transitions
    if new_status == 'voting_open':
        if current_status == 'voting_open':
            st.warning("Voting is already started.")
            return
        if current_status != 'registration_open':
            st.error("Cannot start voting. Registration must be open first.")
            return
    
    if new_status == 'voting_closed':
        if current_status == 'voting_closed' or current_status == 'finalized':
            st.warning("Voting is already closed.")
            return
        if current_status != 'voting_open':
            st.error("Cannot end voting. Voting must be open first.")
            return

    try:
        get_session_ref().update({'status': new_status})
        st.toast(f"Status updated to {new_status.replace('_', ' ').title()}")
        # Force re-authentication flow to refresh data completely (clears cache)
        st.session_state.auth_successful = False 
        st.rerun()
    except Exception as e:
        st.error(f"Failed to update status: {e}")
        
def remove_voter(pii_id):
    """Removes a voter and decrements the counter."""
    try:
        voter_doc = get_voters_collection_ref().document(pii_id).get()
        if voter_doc.exists and voter_doc.to_dict().get('has_voted'):
            st.error("Cannot remove voter who has already cast a vote.")
            return

        get_voters_collection_ref().document(pii_id).delete()
        get_session_ref().update({'voter_count': Increment(-1)})
        st.toast("Voter successfully removed.")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to remove voter: {e}")

# --- UI Flow ---

# Load the current state of the election session
current_session = load_session_data()

# --- 1. SETUP MODE ---
if current_session is None or current_session.get('status') == 'setup_required':
    st.header(f"1. Setup the Single Active Election ({SINGLE_SESSION_ID})")
    st.info("The application requires a one-time setup to start the election.")
    
    with st.form("new_session_form"):
        election_name = st.text_input("Election Title", placeholder="e.g., Annual Board Member Vote 2025")
        candidates_input = st.text_area("Candidates (One per line, Max 10)", placeholder="Candidate A\nCandidate B\nCandidate C")
        
        submitted = st.form_submit_button("Start Election Session", type="primary")

        if submitted:
            candidates_list = [c.strip() for c in candidates_input.split('\n') if c.strip()]
            
            if not election_name or not candidates_list:
                st.error("Please enter both the Election Title and at least one Candidate.")
            elif len(candidates_list) > 10:
                st.error("Maximum 10 candidates are allowed.")
            elif len(set(c.lower() for c in candidates_list)) != len(candidates_list):
                st.error("Candidate names must be unique (case does not matter).")
            else:
                create_new_session(election_name, candidates_list)
    
    if st.session_state.get('new_session_created'):
        st.divider()
        st.header("🔑 CRITICAL: Host Credentials")
        
        # Access the keys from session_data set in create_new_session
        host_pin = st.session_state.session_data.get('host_pin')
        host_private_key = st.session_state.host_private_key
        
        st.warning(f"**Host Private Key** (Secret Mining Key) will NOT be shown again. **Copy this and the PIN immediately.**")
        
        st.code(f"Host PIN: {host_pin}", language="text")
        st.code(host_private_key, language="text")
        
        # Clear the flag to prevent re-display on refresh
        st.session_state['new_session_created'] = False
        st.stop()
    
# --- 2. AUTHENTICATION MODE ---
elif not st.session_state.auth_successful:
    st.header("1. Host Authentication Required")
    st.warning(f"An election named **{current_session['election_name']}** is active. Credentials are required to manage it.")
    
    with st.container(border=True):
        # Using session state variables to hold input values
        st.session_state.host_pin_input = st.text_input("Host PIN", type="password", help="The 6-digit PIN provided during setup.")
        st.session_state.host_private_key_input = st.text_input("Host Private Key (Secret Mining Key)", type="password", help="The long key required to sign blocks.")

        if st.button("Access Portal", type="primary"):
            authenticate_host(
                st.session_state.host_pin_input.strip(), 
                st.session_state.host_private_key_input.strip(),
                current_session
            )
    st.stop()
    
# --- 3. DASHBOARD MODE (Requires Auth) ---

session_data = current_session
host_private_key = st.session_state.host_private_key
current_status = session_data['status']

st.subheader(f"Current Election: {session_data['election_name']}")
st.metric("Election Status", current_status.replace('_', ' ').title())


tab1, tab2, tab3, tab4, tab5 = st.tabs(["Status & Mining", "VoterBase Management", "Blockchain Audit", "Election Results", "Danger Zone"])

# Initialize Blockchain Manager for access across tabs
# The private key is required for mining, but not for viewing/validation
blockchain_manager = Blockchain(
    session_id=SINGLE_SESSION_ID,
    host_public_key=session_data['host_public_key'],
    host_private_key=host_private_key
)

with tab1:
    st.subheader("Control Election Phases")
    col_start, col_end = st.columns(2)
    
    with col_start:
        if st.button("▶️ START VOTING (Ends Registration)", type="primary", disabled=(current_status != 'registration_open')):
            update_session_status(current_status, 'voting_open')
        
    with col_end:
        if st.button("⏹️ END VOTING (Start Tally)", type="primary", disabled=(current_status != 'voting_open')):
            update_session_status(current_status, 'voting_closed')
            
    if current_status == 'voting_open':
        st.info("Registration is closed. Voting is active.")
    elif current_status == 'voting_closed':
        st.warning("Voting is closed. Mine any remaining pending votes, then finalize.")

    st.markdown("---")
    st.subheader("Block Mining Authority (Proof-of-Authority)")
    
    col_metrics, col_mine_action = st.columns(2)

    with col_metrics:
        st.metric("Total Mined Votes", session_data['total_votes'])
        st.metric("Pending Votes (Unmined)", session_data['pending_transactions'], delta_color="inverse")

    with col_mine_action:
        is_mine_disabled = session_data['pending_transactions'] == 0 or current_status == 'finalized' or current_status == 'registration_open'
        if st.button(f"⛏️ MINE {session_data['pending_transactions']} PENDING VOTES INTO NEW BLOCK", type="secondary", disabled=is_mine_disabled):
            try:
                # Use the transactions list from the session data
                blockchain_manager.pending_transactions = session_data.get('pending_transactions_list', [])
                
                # The proof argument is a placeholder in this PoA system, but required by the method signature
                new_block = blockchain_manager.new_block(proof=100) 
                st.success(f"Successfully mined Block #{new_block['index']}! Votes are now permanent.")
                st.toast("Block Mined Successfully!")
                st.session_state.auth_successful = False # Force refresh
                st.rerun() 
            except Exception as e:
                st.error(f"Mining Failed: {e}")
        elif current_status == 'finalized':
            st.info("Election is finalized. No more mining is needed.")
        elif current_status == 'registration_open':
             st.info("Mining is only available when voting has started (Voting Open).")
        elif session_data['pending_transactions'] == 0:
            st.info("No votes are pending to be mined.")

with tab2:
    st.subheader("Private Database Portal: Registered Voter Details")
    st.warning("⚠️ **Contains Sensitive Data**: This portal displays Voter PII, Public Keys, and Secret Private Keys for testing/administrative purposes only.")

    # Stream the collection to get all voters
    voters_data = [doc.to_dict() for doc in get_voters_collection_ref().stream()]
    
    # Sort voters alphabetically by name
    voters_data.sort(key=lambda x: x['name'].lower())

    if voters_data:
        st.metric("Total Registered Voters", len(voters_data))
        
        # Display each voter with all details in an expandable format for easy copying
        for index, voter in enumerate(voters_data):
            
            # Calculate age and format timestamp for display
            age = calculate_age(voter['dob'])
            registered_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(voter['registered_at']))
            status_text = "VOTED ✅" if voter['has_voted'] else "Registered 📝"

            with st.expander(f"👤 **{voter['name']}** ({age} yrs) | Status: **{status_text}**", expanded=False):
                
                col_info, col_keys = st.columns([1, 2])
                
                with col_info:
                    st.markdown("#### PII Information")
                    st.json({
                        "Name": voter['name'],
                        "DOB": voter['dob'],
                        "Age": age,
                        "Registered At": registered_at,
                        "PII Hash ID": voter['pii_id'],
                    })
                    
                with col_keys:
                    st.markdown("#### Voting Keys (Required for Login/Vote)")
                    
                    st.markdown("**Public Key (Voter ID)** - *Used for transaction verification*")
                    st.code(voter['voter_id'], language="text")
                    
                    st.markdown("**Private Key (Secret Wallet Key)** - *Used for digitally signing the vote*")
                    st.code(voter['voter_private_key'], language="text")
                    
                    st.markdown("---")
                    # Removal button at the bottom of the expander
                    if st.button("➖ Remove Voter (If not voted)", key=f"remove_voter_{voter['pii_id']}", type="secondary"):
                        remove_voter(voter['pii_id'])

        st.info("Scroll up to see the details of each voter. Use the code blocks for easy copy/paste.")
    else:
        st.info("No voters have registered yet.")

with tab3:
    st.subheader("Blockchain Ledger Audit (Live Update)")

    # Load chain data, which auto-updates due to the 1s TTL cache
    chain_data = load_chain_data(SINGLE_SESSION_ID)
    
    # We need a temporary Blockchain instance just for validation logic
    temp_blockchain_validator = Blockchain(SINGLE_SESSION_ID, session_data['host_public_key'])
    is_valid = temp_blockchain_validator.is_chain_valid(chain_data)

    if is_valid:
        st.success("✅ Chain Integrity Check: **VALID**. All blocks are linked and signed correctly.")
    else:
        st.error("🛑 Chain Integrity Check: **INVALID**. Tampering detected!")
        
    st.metric("Total Blocks in Chain", len(chain_data))
    
    st.warning("Votes in the ledger are **anonymized** (Public Key hash and Signature) to prevent traceability.")
    
    # Display blocks in reverse chronological order
    for block_data in reversed(chain_data):
        # Create Block object from dictionary to compute the hash dynamically for verification
        block = Block.from_dict(block_data)
        
        # Format timestamp
        timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(block.timestamp))

        with st.expander(f"Block #{block.index} ({len(block.transactions)} votes) - Mined: {timestamp_str}", expanded=False):
            st.code(f"Current Hash: {block.compute_hash()}", language="text")
            st.code(f"Previous Hash: {block.previous_hash}", language="text")
            st.code(f"Host Signature: {block.host_signature[:64]}...", language="text")
            st.markdown("#### Anonymized Transactions:")
            st.json(block.transactions)

with tab4:
    st.markdown("### Election Results Tally (Live Update)")
    
    if current_status not in ['voting_closed', 'finalized']:
        st.info("Results are only displayed after the Host has ended voting.")
        st.stop()
        
    st.metric("Total Mined Votes (Official Count)", session_data['total_votes'])
    st.metric("Pending Votes (Unmined)", session_data['pending_transactions'])
    
    if session_data['total_votes'] > 0:
        st.subheader("Results Tally (Simulated Demo)")
        st.info("The blockchain ensures anonymous voting. This results tally is a **demonstration** based on the total vote count, as true decryption requires complex offline processing.")
        
        # --- Tally Calculation (Simulation) ---
        candidates = session_data.get('candidates', [])
        votes_per_candidate = {}
        remaining_votes = session_data['total_votes']
        
        if candidates:
            # 1. Assign initial random scores
            initial_scores = {c: random.randint(10, 100) for c in candidates}
            initial_sum = sum(initial_scores.values())
            
            # 2. Scale scores to match the actual total_votes
            if initial_sum > 0:
                scale_factor = remaining_votes / initial_sum
                votes_per_candidate = {c: round(score * scale_factor) for c, score in initial_scores.items()}
            else:
                 # Handle case where initial_sum is 0 
                 votes_per_candidate = {c: 0 for c in candidates}
                 if remaining_votes > 0 and candidates:
                     votes_per_candidate[random.choice(candidates)] = remaining_votes


            # 3. Correct any rounding errors to ensure total matches exactly
            current_sum = sum(votes_per_candidate.values())
            difference = remaining_votes - current_sum
            
            if difference != 0 and candidates:
                # Add/subtract the difference from a random candidate
                candidate_to_adjust = random.choice(candidates)
                votes_per_candidate[candidate_to_adjust] += difference
        
        # --- Display Results ---
        if votes_per_candidate:
            df_results = pd.DataFrame(list(votes_per_candidate.items()), columns=['Candidate', 'Votes'])
            df_results = df_results.sort_values(by='Votes', ascending=False).reset_index(drop=True)
            # Calculate and format percentage
            total_votes_sum = df_results['Votes'].sum()
            if total_votes_sum > 0:
                df_results['Percentage'] = (df_results['Votes'] / total_votes_sum * 100).round(2).astype(str) + '%'
            else:
                 df_results['Percentage'] = '0.00%'

            st.markdown("#### Bar Chart Visualization")
            st.bar_chart(df_results.set_index('Candidate')['Votes'])
            
            st.markdown("#### Tally Table")
            st.dataframe(
                df_results, 
                hide_index=True, 
                column_config={
                    "Votes": st.column_config.NumberColumn("Votes", format="%d"),
                    "Candidate": "Candidate",
                    "Percentage": "Percentage"
                }
            )

        else:
            st.info("No votes have been mined yet to show results.")

with tab5:
    st.error("### DANGER ZONE: Reset Election")
    
    col_final, col_reset = st.columns(2)
    
    with col_final:
        st.markdown("#### Finalize Election Status")
        st.warning("Set this status when all pending votes are mined and results are final. Prevents further mining.")
        
        if st.button("FINALIZE ELECTION", type="primary", disabled=(session_data['pending_transactions'] > 0 or current_status == 'finalized')):
            update_session_status(current_status, 'finalized')
        elif session_data['pending_transactions'] > 0:
            st.info("Cannot finalize. Please mine the pending votes first.")

    with col_reset:
        st.markdown("#### Delete All Data")
        st.warning("This action is **PERMANENT** and deletes ALL election data.")

        # Use a temporary session state flag for confirmation
        if st.button("Reset/Delete Election (⚠️ Permanent)", key="reset_election"):
            if st.session_state.get('confirm_reset'):
                try:
                    # 1. Delete the session document
                    get_session_ref().delete() 
                    
                    # 2. Delete all voters
                    for doc in get_voters_collection_ref().stream(): doc.reference.delete()
                    # 3. Delete all blocks
                    for doc in get_blockchain_collection_ref().stream(): doc.reference.delete()
                    
                    st.session_state.clear()
                    st.toast("Election permanently deleted and system reset!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to reset: {e}")
            else:
                st.session_state['confirm_reset'] = True
                st.error("Are you sure? This action is permanent. Click 'Reset/Delete Election (⚠️ Permanent)' again to confirm.")
        
        # Reset the confirmation flag if the user navigates or takes other action
        if 'confirm_reset' in st.session_state and not st.button("I understand, keep me on this page."):
            st.session_state.pop('confirm_reset', None)
