import streamlit as st
import pandas as pd
import time
from datetime import datetime
import uuid
import streamlit.components.v1 as components

# Import local modules
from wallet import generate_key_pair, hash_data, sign_transaction, verify_signature
from database import load_voters, save_voters, load_candidates, save_candidates
import blockchain as bc

# --- Configuration ---
# Hardcoded Host Keys for Proof-of-Authority (PoA)
# These keys sign every block and must remain secret to the host authority.
HOST_PUB = "048259b3f3a1f81c967e81a38a9a46f7c9e05d93335555d496e57c835f11553d102e3b3e346513361e2f79f53e08f5d02322524f2b1d30560b0507a21131713d"
HOST_PRIV = "3a060a87f0b5431665a386119f913d8e3c155d045239a738435d8b80951a87b5"
ELECTION_NAME = "Secured Digital Election"

# --- Setup ---
st.set_page_config(layout="wide", page_title=ELECTION_NAME)
# Set the hardcoded PoA keys in the blockchain module
bc.set_host_keys(HOST_PUB, HOST_PRIV)

# --- State Initialization ---
if 'status' not in st.session_state: st.session_state.status = 'registration_open'
if 'voters' not in st.session_state: st.session_state.voters = load_voters()
if 'candidates' not in st.session_state: st.session_state.candidates = load_candidates()
# Initialize blockchain (creates genesis block if it doesn't exist)
if 'blockchain' not in st.session_state: st.session_state.blockchain = bc.initialize_blockchain()

# --- Helper Functions ---
def calculate_age(dob):
    """Calculates age based on date of birth."""
    today = datetime.now().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

# --- Navigation ---
# Use query params to switch portals: ?portal=host, ?portal=voter, ?portal=private
# This ensures the multi-portal separation works effectively.
query_params = st.query_params
current_portal = query_params.get("portal", "host")

# Sidebar Navigation (Using HTML Links to update query param without full Python rerun issues)
st.sidebar.title("Navigation")
st.sidebar.markdown(f"""
<a href="?portal=host" target="_self"><button style="width:100%;margin-bottom:5px;cursor:pointer;">🏛 Host Portal</button></a>
<a href="?portal=voter" target="_self"><button style="width:100%;margin-bottom:5px;cursor:pointer;">🗳 Voter Portal</button></a>
<a href="?portal=private" target="_self"><button style="width:100%;margin-bottom:5px;cursor:pointer;color:red;">🔑 Private Keys (Admin View)</button></a>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
status_labels = {
    'registration_open': "🟢 Registration Open",
    'voting_open': "🔵 Voting Open",
    'voting_closed': "⚫ Voting Closed"
}
st.sidebar.info(f"Status: {status_labels.get(st.session_state.status)}")

# ==============================================================================
# PORTAL 1: HOST AUTHORITY (Election Management)
# ==============================================================================
if current_portal == 'host':
    st.title("🏛 Host Authority Portal")
    
    # 1. Candidate Management
    st.subheader("1. Candidate Management")
    if st.session_state.status != 'registration_open':
        st.warning("Candidate list is LOCKED.")
        st.write(f"Current Candidates: {', '.join(st.session_state.candidates) if st.session_state.candidates else 'None'}")
    else:
        with st.form("add_candidate"):
            new_cand = st.text_input("New Candidate Name")
            c1, c2 = st.columns(2)
            add = c1.form_submit_button("Add")
            reset = c2.form_submit_button("Reset List")
            
            if add and new_cand:
                norm = new_cand.strip()
                if len(st.session_state.candidates) >= 10:
                    st.error("Max 10 candidates allowed.")
                elif any(c.lower() == norm.lower() for c in st.session_state.candidates):
                    st.error("Candidate already exists.")
                else:
                    st.session_state.candidates.append(norm)
                    save_candidates(st.session_state.candidates)
                    st.success(f"Added {norm}")
                    st.rerun()
            
            if reset:
                st.session_state.candidates = []
                save_candidates([])
                st.rerun()
        
        st.write("Current Candidates:")
        st.dataframe(pd.DataFrame(st.session_state.candidates, columns=["Name"]), hide_index=True)

    st.markdown("---")
    
    # 2. Status Control
    st.subheader("2. Election Status Control")
    c1, c2 = st.columns(2)
    if c1.button("START VOTE"):
        if st.session_state.status == 'voting_open':
            st.warning("Voting is already started.")
        elif st.session_state.status == 'voting_closed':
            st.error("Election finished. Cannot restart.")
        elif len(st.session_state.candidates) < 2:
            st.error("Need at least 2 candidates to start.")
        else:
            st.session_state.status = 'voting_open'
            st.success("Voting Started! Registration is now closed.")
            st.rerun()
            
    if c2.button("END VOTE"):
        if st.session_state.status != 'voting_open':
            st.error("Voting is not currently active.")
        else:
            st.session_state.status = 'voting_closed'
            st.success("Voting Ended! Results are now final.")
            st.rerun()

    st.markdown("---")
    
    # 3. Voter Base Audit
    st.subheader("3. Voter Base Audit")
    
    # Validation Check
    is_valid, block_index, reason = bc.is_chain_valid(st.session_state.blockchain)
    if not is_valid:
        st.error(f"🚨🚨 BLOCKCHAIN CORRUPTED at Block #{block_index}! Reason: {reason} 🚨🚨")
    else:
        st.success("✅ Blockchain Integrity Check: Valid")

    if st.session_state.voters:
        # Prepare display data (exclude private key for host audit)
        display_data = []
        for v in st.session_state.voters:
            display_data.append({
                "Name": v['name'],
                "DOB": v['dob'],
                "Age": calculate_age(datetime.strptime(v['dob'], '%Y-%m-%d').date()),
                "Voted": "✅ Yes" if v['has_voted'] else "❌ No",
                "Public ID (Voter Identity)": v['public_key'][:15] + "...",
                "remove_id": v['public_key'] # Used for removal
            })
        
        st.dataframe(pd.DataFrame(display_data).drop(columns=['remove_id']), hide_index=True)
    else:
        st.info("No voters registered.")

# ==============================================================================
# PORTAL 2: VOTER PORTAL (Registration, Voting, Results)
# ==============================================================================
elif current_portal == 'voter':
    st.title("🗳 Voter Portal")
    
    tab_reg, tab_vote, tab_res, tab_chain = st.tabs(["Registration", "Vote", "Results", "Blockchain"])
    
    # --- Registration Tab ---
    with tab_reg:
        if st.session_state.status != 'registration_open':
            st.warning("Registration is CLOSED.")
        else:
            st.subheader("Register New Voter")
            with st.form("reg_form"):
                name = st.text_input("Full Name")
                dob = st.date_input("Date of Birth", min_value=datetime(1900,1,1).date(), max_value=datetime.now().date())
                submit = st.form_submit_button("Register and Get Keys")
                
                if submit:
                    age = calculate_age(dob)
                    if age < 18:
                        st.error("Ineligible: Must be 18+.")
                    elif len(st.session_state.voters) >= 100:
                        st.error("Max 100 voters reached.")
                    else:
                        # Check duplicate (Name + DOB)
                        dup = any(v['name'].lower() == name.lower() and v['dob'] == str(dob) for v in st.session_state.voters)
                        if dup:
                            st.error("User already registered.")
                        else:
                            priv, pub = generate_key_pair()
                            new_voter = {
                                "name": name,
                                "dob": str(dob),
                                "public_key": pub,
                                "private_key": priv, # Stored in DB for retrieval in Private Admin Portal
                                "has_voted": False
                            }
                            st.session_state.voters.append(new_voter)
                            save_voters(st.session_state.voters)
                            
                            st.success(f"Registration Successful for **{name}**!")
                            st.warning("🛑 CRITICAL: Copy these keys now. You will need them to vote.")
                            st.code(f"Public Key (Voter ID): {pub}", language="text")
                            st.code(f"Private Key (Secret Key): {priv}", language="text")
                            st.info("You can retrieve these keys later in the 'Private Keys (Admin View)' portal.")

    # --- Vote Tab ---
    with tab_vote:
        if st.session_state.status != 'voting_open':
            st.info("Voting is not currently open.")
        elif not st.session_state.candidates:
            st.info("No candidates registered yet.")
        else:
            st.subheader("Cast Your Secure Vote")
            with st.form("cast_vote"):
                v_name = st.text_input("Name (for verification)")
                v_dob = st.date_input("DOB (for verification)", min_value=datetime(1900,1,1).date())
                v_pub = st.text_text_area("Public Key (Voter ID)", height=50)
                v_priv = st.text_area("Private Key (Secret Key)", type="password", height=50)
                choice = st.selectbox("Select Your Candidate", st.session_state.candidates)
                
                vote_btn = st.form_submit_button("Cast Vote Securely")
                
                if vote_btn:
                    # 1. Authentication and Duplicate Check
                    user = next((v for v in st.session_state.voters if v['public_key'] == v_pub.strip()), None)
                    
                    if not user:
                        st.error("Invalid Public Key (Voter ID).")
                    elif user['name'].lower() != v_name.strip().lower() or user['dob'] != str(v_dob):
                        st.error("Name or DOB mismatch with registered record.")
                    elif user['private_key'] != v_priv.strip():
                        st.error("Invalid Private Key (Secret Key).")
                    elif user['has_voted']:
                        st.error("You have already voted! Double-voting detected.")
                    else:
                        # 2. Process Vote and Sign Transaction
                        
                        # Data to be signed (must be unique and verifiable)
                        data_to_sign = f"VOTE|{v_pub.strip()}|{choice}|{time.time()}"
                        data_hash = hash_data(data_to_sign)
                        
                        # Voter signs the data hash with their private key
                        sig = sign_transaction(v_priv.strip(), data_hash)
                        
                        # 3. Verification (Crucial security step)
                        if verify_signature(v_pub.strip(), data_hash, sig):
                            
                            # 4. Create Transaction and Mine Block
                            # Note: The transaction only stores the verifiable parts (candidate and signature)
                            tx_data = {
                                "candidate": choice,
                                "voter_public_key": v_pub.strip(), # Stored for non-repudiation
                                "signature": sig,
                                "timestamp": time.time()
                            }
                            bc.new_block(st.session_state.blockchain, [tx_data])
                            
                            # 5. Update DB status to prevent future votes
                            for v in st.session_state.voters:
                                if v['public_key'] == v_pub.strip():
                                    v['has_voted'] = True
                                    break
                            save_voters(st.session_state.voters)
                            
                            st.success("✅ Vote Cast and Secured on the Blockchain!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Digital Signature verification failed. Vote rejected.")

    # --- Results Tab ---
    with tab_res:
        st.subheader("Election Results")
        if st.session_state.status != 'voting_closed':
            st.info("Preliminary results are displayed during voting, but the final tally requires the Host to end the election.")
        
        counts = {c: 0 for c in st.session_state.candidates}
        total_votes = 0
        
        # Tally results by traversing the blockchain
        for block in st.session_state.blockchain:
            if block['index'] == 1: continue # Skip genesis
            for tx in block['transactions']:
                cand = tx.get('candidate')
                if cand in counts:
                    counts[cand] += 1
                    total_votes += 1
        
        st.metric(label="Total Votes Cast", value=total_votes)
        
        if total_votes > 0:
            results_df = pd.DataFrame.from_dict(counts, orient='index', columns=['Votes'])
            st.bar_chart(results_df)
            st.dataframe(results_df)
        else:
            st.warning("No votes recorded yet.")


    # --- Ledger Tab ---
    with tab_chain:
        st.subheader("Immutable Blockchain Ledger (Audit View)")
        is_valid, block_index, reason = bc.is_chain_valid(st.session_state.blockchain)
        
        if not is_valid:
            st.error(f"🚨 BLOCKCHAIN INTEGRITY BREACH: Chain is invalid at Block #{block_index}. Reason: {reason}")
        else:
            st.success("✅ Chain is Valid: All blocks are correctly linked and Host-signed.")

        st.info("The ledger proves the votes were recorded in the correct order and signed by the Host Authority.")
        
        for block in reversed(st.session_state.blockchain):
            with st.expander(f"Block #{block['index']} | Hash: {block['hash'][:10]}..."):
                st.json(block)

# ==============================================================================
# PORTAL 3: PRIVATE KEYS (Admin View - Simulating Secure Delivery/Retrieval)
# ==============================================================================
elif current_portal == 'private':
    st.title("🔑 Private Keys Database (Admin Retrieval View)")
    st.header("Voter Credentials List")
    st.warning("This page simulates the Host's secure access to voter credentials (e.g., if a voter loses their key). In a production system, this data should be encrypted or delivered once and deleted.")
    
    if not st.session_state.voters:
        st.info("No voters registered yet.")
    else:
        # Display as a table first
        display_keys = []
        for v in st.session_state.voters:
            display_keys.append({
                "Name": v['name'],
                "Voted": v['has_voted'],
                "Public Key (Voter ID)": v['public_key'],
                "Private Key (Secret)": v['private_key'],
            })
        
        st.dataframe(pd.DataFrame(display_keys), hide_index=True)
        st.markdown("---")
        st.subheader("Individual Key View")
        
        # Display individual key containers for easier copying
        for v in st.session_state.voters:
            with st.container(border=True):
                st.markdown(f"**Voter: {v['name']}** (Voted: {'Yes' if v['has_voted'] else 'No'})")
                
                # Use separate text areas for easy copying
                st.text_area(f"Public Key for {v['name']}", v['public_key'], height=3, key=f"pub_key_{v['public_key']}")
                st.text_area(f"Private Key for {v['name']}", v['private_key'], height=3, key=f"priv_key_{v['public_key']}")
