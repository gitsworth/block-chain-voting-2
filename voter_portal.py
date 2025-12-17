import streamlit as st
from firestore_service import get_candidates, check_voter_voted, record_vote_document
from blockchain_core import get_blockchain

def render_voter_portal():
    """Renders the Voter portal."""
    voter_id = st.session_state.context_id
    
    st.title(f"Voter Portal (ID: {voter_id})")
    st.info("You are authenticated. You may cast one vote.")
    
    st.markdown("---")
    st.subheader("🗳️ Vote for a Candidate")

    candidates, _ = get_candidates()
    has_voted = check_voter_voted(voter_id)

    if not candidates:
        st.warning("Voting is not open yet. Awaiting Host setup.")
        return

    if has_voted:
        st.success("✅ You have already cast your vote. Thank you!")
        st.markdown("---")
        st.subheader("Current Results Preview")
        # Display simplified results preview
        for candidate in candidates:
             st.write(f"- {candidate['name']} ({candidate['voteCount']} votes)")
    else:
        st.warning("Please select a candidate below to cast your vote.")
        
        for candidate in candidates:
            if st.button(f"Vote for {candidate['name']}", key=f"vote_{candidate['id']}", use_container_width=True, disabled=has_voted):
                # Confirmation is required before recording
                if st.session_state.get('confirm_vote') == candidate['id']:
                    # Final confirmation
                    vote_doc_id = record_vote_document(voter_id, candidate['id'], candidate['name'])
                    if vote_doc_id:
                        # Add to pending blockchain transactions
                        bc = get_blockchain()
                        bc.new_transaction(voter_id, vote_doc_id, 1)

                        st.session_state.confirm_vote = None # Reset confirmation
                        st.success(f"Vote confirmed for {candidate['name']}! Awaiting blockchain validation.")
                        st.experimental_rerun()
                    else:
                        st.error("Failed to record vote document.")
                else:
                    # First click asks for confirmation
                    st.session_state.confirm_vote = candidate['id']
                    st.warning(f"Click 'Vote for {candidate['name']}' again to confirm your final vote.")
