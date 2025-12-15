import streamlit as st
import pandas as pd
from datetime import date
from voting_system import get_system, hash_data, MIN_VOTING_AGE

st.set_page_config(layout="wide", page_title="Voter Portal")
system = get_system()

# --- Helper function for displaying keys ---
def display_keys(title, key_text):
    st.subheader(title)
    st.code(key_text, language='text')

# --- UI Header and Status ---

st.title("🗳️ Voter Portal")
st.caption("Register, cast your vote, and view election transparency.")

st.markdown(f"### Current Phase: :orange[{st.session_state.election_phase.upper()}]")
st.divider()

# --- Main Tabs ---
tab_register, tab_vote, tab_election, tab_blockchain = st.tabs([
    "Register", "Cast Vote", "Election Results", "Blockchain View"
])

with tab_register:
    st.header("Voter Registration")
    
    if st.session_state.election_phase != 'registration':
        st.warning("Registration is closed. You can proceed to the 'Cast Vote' tab.")
    else:
        if len(st.session_state.voters) >= 100:
            st.error("Maximum voter capacity reached. Registration is now closed.")
        else:
            with st.form("registration_form", clear_on_submit=True):
                st.subheader("Your Information")
                col_name, col_dob = st.columns(2)
                
                with col_name:
                    v_name = st.text_input("Full Name (Case does not matter)")
                with col_dob:
                    v_dob = st.date_input("Date of Birth", min_value=date(1900, 1, 1), max_value=date.today())
                
                submitted = st.form_submit_button("Register and Get Keys", type="primary")

                if submitted:
                    if not v_name or not v_dob:
                        st.error("Please fill in all fields.")
                    else:
                        success, message = system.register_voter(v_name.strip(), datetime(v_dob.year, v_dob.month, v_dob.day))
                        
                        if success:
                            st.success(f"{message} Please save your keys securely!")
                            
                            # Find the new voter's data
                            new_voter = next(v for v in st.session_state.voters if v['name'].lower() == v_name.lower() and v['dob'] == v_dob.strftime("%Y-%m-%d"))
                            
                            with st.expander("🔑 Your Generated Keys (Copy and Save Securely!)", expanded=True):
                                display_keys("Public Key", new_voter['pub_key'])
                                display_keys("Private Key", new_voter['priv_key'])
                        else:
                            if "Ineligible" in message:
                                st.error(message)
                            else:
                                st.warning(message)

with tab_vote:
    st.header("Cast Your Vote")

    if st.session_state.election_phase == 'registration':
        st.info("Voting has not started yet. Check back after the host starts the election.")
    elif st.session_state.election_phase == 'ended':
        st.warning("Voting has ended. Please view the results tab.")
    else:
        if not st.session_state.candidates:
            st.error("No candidates are registered. Voting cannot proceed.")
        else:
            with st.form("voting_form", clear_on_submit=True):
                st.subheader("Voter Authentication")
                col_n_d, col_k = st.columns(2)
                
                with col_n_d:
                    v_name_v = st.text_input("Full Name (Registered Name)")
                    v_dob_v = st.date_input("Date of Birth", min_value=date(1900, 1, 1), max_value=date.today())
                
                with col_k:
                    v_pub_key = st.text_area("Public Key", height=150)
                    v_priv_key = st.text_area("Private Key", height=150)
                
                st.divider()
                st.subheader("Select Candidate")
                candidate_names = [c['name'] for c in st.session_state.candidates]
                v_candidate = st.radio("Candidate of Choice", candidate_names)
                
                submitted = st.form_submit_button("CAST VOTE", type="primary")

                if submitted:
                    if not v_name_v or not v_dob_v or not v_pub_key or not v_priv_key:
                        st.error("All authentication fields and key fields must be filled.")
                    else:
                        dob_str = v_dob_v.strftime("%Y-%m-%d")
                        success, message = system.authenticate_and_vote(v_name_v.strip(), dob_str, v_pub_key.strip(), v_priv_key.strip(), v_candidate)
                        
                        if success:
                            st.balloons()
                            st.success(message)
                        else:
                            st.error(message)

# The Election Results and Blockchain tabs are identical to the Host Portal for transparency
with tab_election:
    st.header("Election Results")
    
    if st.session_state.election_phase != 'ended':
        st.warning("Results are available only after the election has ended.")
    else:
        # Display logic identical to Host Portal
        if not st.session_state.candidates:
            st.info("No candidates were registered for this election.")
        else:
            df_results = pd.DataFrame(st.session_state.candidates).sort_values(by='votes', ascending=False).reset_index(drop=True)
            total_votes = df_results['votes'].sum()
            st.metric(label="Total Votes Cast", value=total_votes)
            st.divider()
            st.subheader("Final Tally")
            st.dataframe(df_results, hide_index=True, use_container_width=True)

with tab_blockchain:
    st.header("Blockchain Ledger (Live View)")
    st.info("This ledger contains anonymized, encrypted votes. The integrity of the election is secured by this chain.")
    
    chain_data = []
    for block in system.st.session_state.blockchain.chain:
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
