# app.py - Main Streamlit application for the Secure Blockchain Voting System
import streamlit as st
import pandas as pd
import time
import json
from datetime import datetime
from google.cloud import firestore # Needed for firestore query access

# --- Local Modules (Firestore, Crypto, Blockchain) ---
# Note: firestore_config is loaded first to ensure the 'db' client is ready
from firestore_config import db, get_session_ref, get_voters_collection_ref, SINGLE_SESSION_ID
from wallet import generate_key_pair, sign_data, verify_signature, get_pii_id
from blockchain import Blockchain

# --- CRITICAL CONFIGURATION ---
# These keys are required for the Host Authority (PoA consensus). 
# We use known-good keys temporarily as key generation outside the app is difficult in this environment.
HOST_PUBLIC_KEY = "04f9812f864e29c8e29a99f18731d1020786522c07342921b777a824100c5c7d0d6118d052d9a3028211b714f3b573e35a11956e300109968412030040682121"
HOST_PRIVATE_KEY = "c8b4b74581f1d19d7e5d263a568c078864d2d4808386375354972e25d25e0c50"

# --- GLOBAL STATE & CACHING ---
@st.cache_resource
def initialize_system():
    """Initializes the Blockchain manager and Firestore references."""
    if db is None:
        st.error("FATAL: Firestore client failed to initialize. Check firestore_config.py.")
        return None, None
        
    blockchain_manager = Blockchain(
        session_id=SINGLE_SESSION_ID,
        host_public_key=HOST_PUBLIC_KEY,
        host_private_key=HOST_PRIVATE_KEY
    )
    
    # Attempt to initialize chain (create genesis block if needed)
    try:
        blockchain_manager.initialize_blockchain()
    except Exception as e:
        st.error(f"Error initializing blockchain: {e}")

    return blockchain_manager, get_session_ref()

BLOCKCHAIN_MANAGER, SESSION_REF = initialize_system()

# --- HELPER FUNCTIONS FOR FIRESTORE INTERACTION ---

def load_session_data():
    """Fetches the session metadata from Firestore."""
    try:
        session_doc = SESSION_REF.get()
        if session_doc.exists:
            data = session_doc.to_dict()
            return {
                'phase': data.get('phase', 'SETUP'),
                'candidates': data.get('candidates', []),
                'total_votes': data.get('total_votes', 0),
                'pending_transactions': data.get('pending_transactions', 0)
            }
        else:
            # Initialize default session data if document doesn't exist
            initial_data = {'phase': 'SETUP', 'candidates': [], 'total_votes': 0, 'pending_transactions': 0}
            SESSION_REF.set(initial_data)
            return initial_data
    except Exception as e:
        st.error(f"Error loading session data: {e}")
        return {'phase': 'SETUP', 'candidates': [], 'total_votes': 0, 'pending_transactions': 0}

def load_voters():
    """Fetches all registered voters from Firestore."""
    voters_collection = get_voters_collection_ref()
    try:
        docs = voters_collection.stream()
        voters_list = [doc.to_dict() for doc in docs]
        return pd.DataFrame(voters_list)
    except Exception as e:
        st.error(f"Error loading voter data: {e}")
        return pd.DataFrame()

def update_voter_status(voter_id, has_voted=True):
    """Updates the 'has_voted' status for a voter in Firestore."""
    voter_ref = get_voters_collection_ref().document(voter_id)
    try:
        voter_ref.update({'has_voted': has_voted})
        return True
    except Exception as e:
        st.error(f"Error updating voter status: {e}")
        return False

# --- UI COMPONENTS (Portal Functions) ---

def host_portal(session_data, voters_df):
    """Interface for the Election Host Authority."""
    st.header("🏛 Host Authority Portal")
    current_phase = session_data['phase']
    st.subheader(f"Current Election Phase: **{current_phase}**")
    
    # --- 1. Phase Control ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Election Control")

    if current_phase == 'SETUP':
        if st.sidebar.button("▶️ Open Registration"):
            SESSION_REF.update({'phase': 'REGISTRATION'})
            st.rerun()
            
    elif current_phase == 'REGISTRATION':
        if st.sidebar.button("🗳️ Open Voting"):
            if not session_data['candidates']:
                st.error("Cannot open voting: Please add at least one candidate.")
            else:
                SESSION_REF.update({'phase': 'VOTING'})
                st.rerun()
                
    elif current_phase == 'VOTING':
        if st.sidebar.button("🛑 Close Voting"):
            SESSION_REF.update({'phase': 'CLOSED'})
            st.rerun()
    
    # --- 2. Candidate Management ---
    st.subheader("Candidate Management")
    if current_phase in ['SETUP', 'REGISTRATION']:
        new_candidate = st.text_input("New Candidate Name:")
        if st.button("Add Candidate"):
            if new_candidate and new_candidate not in session_data['candidates']:
                new_list = session_data['candidates'] + [new_candidate]
                SESSION_REF.update({'candidates': new_list})
                st.rerun()
            elif new_candidate in session_data['candidates']:
                st.warning("Candidate already exists.")
            else:
                st.error("Please enter a name.")

    if session_data['candidates']:
        st.write("Current Candidates:")
        st.info(", ".join(session_data['candidates']))
        
    # --- 3. Voter Registration ---
    st.subheader("Voter Registration")
    if current_phase == 'REGISTRATION':
        with st.form("voter_registration"):
            new_name = st.text_input("Full Name:")
            new_dob = st.date_input("Date of Birth (YYYY-MM-DD):", format="YYYY-MM-DD")
            new_email = st.text_input("Email (for PII uniqueness):")
            submitted = st.form_submit_button("Register Voter & Generate Keys")
            
            if submitted:
                if not new_name or not new_email:
                    st.error("Name and Email are required.")
                else:
                    # 1. Generate PII ID and check for existing voter
                    pii_id = get_pii_id(new_name, str(new_dob), new_email)
                    voter_ref = get_voters_collection_ref().document(pii_id)
                    if voter_ref.get().exists:
                         st.warning("This voter (based on Name/DOB/Email) is already registered.")
                    else:
                        # 2. Generate Cryptographic Key Pair
                        private_key, public_key = generate_key_pair()
                        
                        # 3. Create Voter Document
                        new_voter = {
                            'id': pii_id, # PII ID (for Host management)
                            'name': new_name,
                            'dob': str(new_dob),
                            'email': new_email,
                            'public_key': public_key, # Voter ID on ledger
                            'private_key': private_key, # Secret for signing
                            'has_voted': False
                        }
                        
                        try:
                            voter_ref.set(new_voter)
                            st.success(f"Voter **{new_name}** registered successfully!")
                            st.warning("IMPORTANT: Securely deliver these credentials to the voter.")
                            st.code(f"Public Key (Voter ID): {public_key}", language="text")
                            st.code(f"Private Key (Secret Key): {private_key}", language="text")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save voter: {e}")
    
    # --- 4. Registered Voter List ---
    st.subheader(f"Registered Voters ({len(voters_df)})")
    if not voters_df.empty:
        # Display only non-sensitive columns
        display_df = voters_df[['name', 'public_key', 'has_voted']].copy()
        display_df.rename(columns={'public_key': 'Voter ID (Public Key)', 'has_voted': 'Voted Status'}, inplace=True)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No voters registered yet.")

    # --- 5. Transaction Mining (PoA) ---
    st.markdown("---")
    st.subheader("PoA Mining & Ledger Finalization")
    
    pending_count = session_data['pending_transactions']
    if pending_count > 0 and current_phase == 'VOTING':
        st.warning(f"🚨 {pending_count} pending vote(s) awaiting finalization!")
        if st.button(f"Mine New Block ({pending_count} Transactions)"):
            try:
                # Proof of Authority: Mine a new block signed by the Host
                BLOCKCHAIN_MANAGER.new_block(proof=0)
                st.success(f"New Block Mined! {pending_count} votes finalized on the ledger.")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"Mining Failed: {e}")
    else:
        st.info("No pending votes. Ledger is up-to-date.")


def voter_portal(session_data, voters_df):
    """Interface for the Voter to cast a vote."""
    st.header("🗳️ Voter Portal")
    current_phase = session_data['phase']
    
    if current_phase != 'VOTING':
        st.info(f"Voting is currently {current_phase}.")
        return

    st.subheader("Casting Your Secure Vote")
    
    voter_data = {}
    
    # --- 1. Authentication ---
    with st.form("voter_auth"):
        input_public_key = st.text_input("Voter ID (Public Key):")
        input_private_key = st.text_input("Secret Wallet Key (Private Key):", type="password")
        auth_submitted = st.form_submit_button("Authenticate")

        if auth_submitted:
            if input_public_key not in voters_df['public_key'].values:
                st.error("Authentication failed: Invalid Voter ID.")
            else:
                voter_record = voters_df[voters_df['public_key'] == input_public_key].iloc[0]
                
                # Check 1: Private Key Match (Authentication)
                if voter_record['private_key'] != input_private_key:
                    st.error("Authentication failed: Private Key incorrect.")
                
                # Check 2: Double Voting
                elif voter_record['has_voted']:
                    st.error("You have already cast your vote. Double voting is prevented.")
                
                else:
                    # Successful Authentication: Save keys to session state
                    st.session_state['authenticated_voter'] = voter_record.to_dict()
                    st.session_state['voter_keys'] = {'public': input_public_key, 'private': input_private_key}
                    st.success(f"Authentication Successful! Welcome, {voter_record['name']}.")
                    st.rerun()
    
    # If authenticated, show the voting form
    if 'authenticated_voter' in st.session_state and st.session_state['authenticated_voter'].get('public_key') == st.session_state['voter_keys']['public']:
        voter_info = st.session_state['authenticated_voter']
        st.success(f"Ready to vote: Logged in as {voter_info['name']}")
        
        candidates = session_data['candidates']
        if not candidates:
            st.error("No candidates are registered for this election.")
            return

        with st.form("vote_casting"):
            selected_candidate = st.radio("Select your candidate:", candidates)
            vote_submitted = st.form_submit_button("Cast Secure Vote")
            
            if vote_submitted:
                voter_id = voter_info['public_key']
                private_key = voter_info['private_key']
                
                # 1. Create Transaction Data (the data to be signed)
                vote_data = f"{voter_id}|{selected_candidate}|{datetime.now().isoformat()}"
                
                # 2. Digital Signing (Voter's Private Key)
                signature = sign_data(private_key, vote_data)
                
                # 3. Self-Verification (Crucial step for integrity check before submission)
                if not verify_signature(voter_id, vote_data, signature):
                    st.error("Internal Error: Signature verification failed. Vote aborted.")
                    return
                
                # 4. Submit Transaction to Blockchain Pool
                BLOCKCHAIN_MANAGER.add_transaction(voter_id, selected_candidate, signature)
                
                # 5. Update Voter Status in Firestore
                if update_voter_status(voter_info['id'], has_voted=True):
                    # Clear auth state to force re-login/prevent multiple votes in this session
                    del st.session_state['authenticated_voter']
                    del st.session_state['voter_keys']
                    
                    st.success(f"Vote successfully cast! Your transaction is pending mining on the ledger.")
                    st.info("Please wait for the Host to mine the next block to finalize your vote.")
                    st.rerun()
                else:
                    st.error("Failed to update voter status (double-voting prevention). Vote submission aborted.")
                    

def results_portal(session_data):
    """Interface to view election results based on the validated blockchain."""
    st.header("📊 Election Results & Tally")
    
    if session_data['phase'] != 'CLOSED':
        st.info(f"Results are finalized when voting is closed. Current phase: {session_data['phase']}")
        return
        
    st.subheader("Official Election Tally")
    
    # --- 1. Load and Analyze Blockchain ---
    try:
        # Load all blocks from the chain
        chain_docs = BLOCKCHAIN_MANAGER.chain_ref.order_by("index", direction=firestore.Query.ASCENDING).stream()
        chain_data = [doc.to_dict() for doc in chain_docs]
    except Exception as e:
        st.error(f"Error loading blockchain data: {e}")
        return

    if not chain_data:
        st.warning("Blockchain is empty.")
        return

    # Check the chain integrity before tallying
    is_valid = BLOCKCHAIN_MANAGER.is_chain_valid(chain_data)
    
    if not is_valid:
        st.error("🚨 CRITICAL ALERT: Blockchain integrity check failed! Results cannot be trusted.")
        return

    # --- 2. Tally Votes ---
    st.success("✅ Blockchain Integrity Verified: Chain is valid and tamper-free.")
    
    voted_voters = set()
    vote_tallies = {}
    total_valid_votes = 0
    
    # Iterate through all blocks (skipping genesis)
    for block_data in chain_data[1:]:
        for tx in block_data.get('transactions', []):
            voter_id = tx.get('voter_id')
            candidate = tx.get('candidate')
            
            if not voter_id or not candidate:
                continue

            # Tally votes, enforcing one vote per voter ID
            if voter_id not in voted_voters:
                voted_voters.add(voter_id)
                vote_tallies[candidate] = vote_tallies.get(candidate, 0) + 1
                total_valid_votes += 1
            # Note: We don't mark as invalid here, as the double-voting check should have been done
            # by the app before submission, but this ensures the tally is unique.
    
    # --- 3. Display Results ---
    st.markdown(f"**Total Valid Votes Counted:** {total_valid_votes}")
    
    if not vote_tallies:
        st.info("No votes recorded in the ledger.")
        return
        
    results_df = pd.DataFrame(
        list(vote_tallies.items()), 
        columns=['Candidate', 'Votes']
    ).sort_values(by='Votes', ascending=False)
    
    # Calculate Percentage
    results_df['Percentage'] = (results_df['Votes'] / total_valid_votes) * 100
    results_df['Percentage'] = results_df['Percentage'].round(2).astype(str) + '%'
    
    st.dataframe(results_df, use_container_width=True, hide_index=True)
    
    # Declare Winner
    winner = results_df.iloc[0]['Candidate']
    st.balloons()
    st.success(f"🏆 The Winner is: **{winner}** with {results_df.iloc[0]['Votes']} votes!")
    
    # Display Chart
    st.bar_chart(results_df.set_index('Candidate')['Votes'])


def ledger_portal():
    """Interface to view the raw blockchain blocks."""
    st.header("🔗 Blockchain Ledger Audit")
    st.info("This view allows full transparency by displaying the raw, signed blocks.")
    
    # --- 1. Load and Display Blockchain ---
    try:
        # Load all blocks from the chain
        chain_docs = BLOCKCHAIN_MANAGER.chain_ref.order_by("index", direction=firestore.Query.ASCENDING).stream()
        chain_data = [doc.to_dict() for doc in chain_docs]
    except Exception as e:
        st.error(f"Error loading blockchain data: {e}")
        return

    if not chain_data:
        st.warning("Blockchain is empty. The Host must create the Genesis Block first.")
        return

    # Check the chain integrity before displaying
    is_valid = BLOCKCHAIN_MANAGER.is_chain_valid(chain_data)
    
    if not is_valid:
        st.error("🚨 CRITICAL ALERT: Blockchain integrity check failed! Ledger data may be compromised.")
    else:
        st.success("✅ Ledger Integrity Verified: All block hashes and Host signatures are correct.")

    # --- 2. Display Blocks in Expander ---
    st.subheader(f"Total Blocks in Chain: {len(chain_data)}")
    
    for i, block_data in enumerate(chain_data):
        block_obj = BLOCKCHAIN_MANAGER.Block.from_dict(block_data)
        
        with st.expander(f"Block #{i} (Timestamp: {datetime.fromtimestamp(block_obj.timestamp).strftime('%Y-%m-%d %H:%M:%S')})"):
            st.markdown(f"**Index:** `{block_obj.index}`")
            st.markdown(f"**Host Public Key:** `{block_obj.host_public_key}`")
            st.markdown(f"**Previous Hash:** `{block_obj.previous_hash}`")
            st.markdown(f"**Block Hash (Calculated):** `{block_obj.hash}`")
            
            # Signature Verification Status
            is_sig_valid = verify_signature(
                block_obj.host_public_key, 
                block_obj.compute_hash(), 
                block_obj.host_signature
            )
            
            if is_sig_valid:
                st.markdown(f"**Host Signature:** ✅ Valid")
            else:
                st.markdown(f"**Host Signature:** ❌ FAILED")
                
            st.markdown("---")
            st.markdown(f"**Transactions ({len(block_obj.transactions)}):**")
            if block_obj.transactions:
                tx_df = pd.DataFrame(block_obj.transactions)
                # Display only relevant transaction fields for audit
                st.dataframe(tx_df[['voter_id', 'candidate', 'timestamp']], use_container_width=True)
            else:
                st.info("No transactions in this block (Genesis or empty block).")
    
# --- MAIN APP LOGIC ---

def main():
    """The main Streamlit application layout."""
    st.set_page_config(layout="wide", page_title="Secure Blockchain Voting System")
    
    st.title("Secure Blockchain Voting System (PoA/Firestore)")
    st.caption(f"Using Session ID: **{SINGLE_SESSION_ID}** | Host Public Key: `{HOST_PUBLIC_KEY[:10]}...`")

    # Load shared data once per rerun
    session_data = load_session_data()
    voters_df = load_voters()
    
    if voters_df.empty:
        total_voters = 0
    else:
        total_voters = len(voters_df)

    # --- Metrics Display ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Voters Registered", total_voters)
    col2.metric("Votes Finalized on Ledger", session_data['total_votes'])
    col3.metric("Pending Transactions", session_data['pending_transactions'])
    col4.metric("Candidates", len(session_data['candidates']))
    
    st.markdown("---")

    # --- Tab Navigation ---
    tab_host, tab_voter, tab_ledger, tab_results = st.tabs([
        "🏛 Host Portal", 
        "🗳️ Voter Portal", 
        "🔗 Blockchain Ledger", 
        "📊 Election Results"
    ])

    with tab_host:
        host_portal(session_data, voters_df)

    with tab_voter:
        voter_portal(session_data, voters_df)

    with tab_ledger:
        ledger_portal()

    with tab_results:
        results_portal(session_data)

if __name__ == "__main__":
    main()
