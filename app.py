import streamlit as st
import pandas as pd
from voting_system import get_system, MAX_CANDIDATES, hash_data

st.set_page_config(layout="wide", page_title="Host Portal - Blockchain Election")
system = get_system()

# --- Utility for Copy Button (Streamlit workaround) ---
def create_copy_button(text_to_copy: str, key: str):
    """Creates a button that copies text to the clipboard."""
    st.button("📋 Copy", on_click=None, args=None, key=key, help="Copies the key to clipboard")
    if st.session_state.get(key):
        # Using st.code with a tiny font size for the actual key text
        st.code(text_to_copy, language='text', line_numbers=False)
        st.toast(f"Copied key: {text_to_copy[:15]}...", icon="✅")

# --- UI Header and Status ---

st.title("🛡️ Host Portal (Admin Dashboard)")
st.caption("Manage candidates, control the election phases, and monitor results/blockchain.")

phase_color = {'registration': 'blue', 'voting': 'orange', 'ended': 'red'}
st.markdown(f"### Current Phase: :orange[{st.session_state.election_phase.upper()}]", 
            unsafe_allow_html=True)
st.divider()

# --- Main Tabs ---
tab_host, tab_voterbase, tab_election, tab_blockchain = st.tabs([
    "Host Control", "Voterbase", "Election Results", "Blockchain Ledger"
])

with tab_host:
    st.header("Candidate and Election Control")
    col_setup, col_list = st.columns([1, 1])

    with col_setup:
        st.subheader("Add Candidate")
        with st.form("candidate_form", clear_on_submit=True):
            candidate_name = st.text_input("Candidate Name", 
                                            placeholder="Enter unique name", 
                                            disabled=st.session_state.election_phase != 'registration')
            submitted = st.form_submit_button("Add Candidate", 
                                              disabled=st.session_state.election_phase != 'registration')
            if submitted and candidate_name:
                message = system.add_candidate(candidate_name.strip())
                st.info(message)
    
    with col_list:
        st.subheader(f"Candidates ({len(st.session_state.candidates)}/{MAX_CANDIDATES})")
        
        if not st.session_state.candidates:
            st.info("No candidates added yet.")
        else:
            df_candidates = pd.DataFrame(st.session_state.candidates)
            st.dataframe(df_candidates[['name']], hide_index=True, use_container_width=True)

    st.subheader("Phase Control")
    col_start, col_end = st.columns(2)
    
    with col_start:
        if st.button("🔴 START VOTE", use_container_width=True, type="primary"):
            message = system.start_vote()
            st.toast(message)
            st.rerun()

    with col_end:
        if st.button("⚫ END VOTE", use_container_width=True, type="secondary"):
            message = system.end_vote()
            st.toast(message)
            st.rerun()

with tab_voterbase:
    st.header("Registered Voter Database (No Private Keys)")
    
    df_voters = pd.DataFrame(st.session_state.voters)
    
    if df_voters.empty:
        st.info("No voters registered yet.")
    else:
        # Prepare data for display and removal (without priv_key)
        df_display = df_voters.copy()
        df_display['voter_id'] = df_display.apply(lambda row: f"{row['dob']} - {hash_data(row['pub_key'])[:6]}...", axis=1)
        df_display['pub_key_hash'] = df_display['pub_key'].apply(lambda x: hash_data(x))
        df_display = df_display[['name', 'dob', 'has_voted', 'pub_key_hash']]

        st.subheader(f"Total Registered Voters: {len(df_voters)}")

        # Data editor for removal
        edited_df = st.data_editor(
            df_display,
            column_config={
                "pub_key_hash": st.column_config.Column("Public Key Hash", disabled=True),
                "dob": st.column_config.Column("DOB", disabled=True),
            },
            hide_index=True,
            num_rows="dynamic",
            use_container_width=True
        )

        # Check for removed rows
        removed_rows = df_display[~df_display.isin(edited_df)].dropna(how='all')
        if not removed_rows.empty:
            removed_dob = removed_rows.iloc[0]['dob']
            removed_pub_key_hash = removed_rows.iloc[0]['pub_key_hash']
            
            # Find the original voter record to get the full public key
            voter_to_remove = df_voters[(df_voters['dob'] == removed_dob) & 
                                        (df_voters['pub_key'].apply(hash_data) == removed_pub_key_hash)].iloc[0]
            
            system.remove_voter(voter_to_remove['dob'], voter_to_remove['pub_key'])
            st.toast(f"Voter removed: {voter_to_remove['name']} ({voter_to_remove['dob']})", icon="🗑️")
            st.rerun()

with tab_election:
    st.header("Election Results")
    
    if st.session_state.election_phase != 'ended':
        st.warning("Results are available only after the election has ended.")
    else:
        if not st.session_state.candidates:
            st.info("No candidates were registered for this election.")
        else:
            df_results = pd.DataFrame(st.session_state.candidates).sort_values(by='votes', ascending=False).reset_index(drop=True)
            
            total_votes = df_results['votes'].sum()
            st.metric(label="Total Votes Cast (Valid Blockchain Transactions)", value=total_votes)
            st.divider()
            
            st.subheader("Final Tally")
            st.dataframe(df_results, hide_index=True, use_container_width=True)

            if total_votes > 0:
                winner = df_results.iloc[0]
                st.success(f"🏆 Winner: **{winner['name']}** with **{winner['votes']}** votes!")

with tab_blockchain:
    st.header("Blockchain Ledger (Live View)")
    st.info("This ledger contains anonymized, encrypted votes. Voter identity is obscured by hashing, and the vote is encrypted with the voter's public key.")
    
    chain_data = []
    for block in system.get_system().st.session_state.blockchain.chain:
        # Display only essential, non-traceable data
        display_data = {
            'Index': block.index,
            'Timestamp': block.timestamp,
            'Voter Pub Key Hash': block.data.get('voter_pub_key_hash', 'N/A'),
            'Encrypted Vote': block.data.get('encrypted_vote', 'N/A')[:50] + '...', # Truncate for display
            'Previous Hash': block.previous_hash[:15] + '...',
            'Current Hash': block.hash[:15] + '...'
        }
        chain_data.append(display_data)

    df_chain = pd.DataFrame(chain_data)
    
    st.subheader(f"Total Blocks: {len(df_chain)}")
    st.dataframe(df_chain, hide_index=True, use_container_width=True)
