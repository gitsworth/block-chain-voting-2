import streamlit as st
from firestore_service import add_candidate, get_candidates

def render_host_portal():
    """Renders the Host (Admin) portal."""
    role = st.session_state.user_role
    context_id = st.session_state.context_id
    
    st.title(f"Host Portal ({context_id})")
    st.info(f"Host Private Key: `{context_id}` (Keep this secure)")
    
    st.subheader("🗳️ Voting Management: Add Candidate")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        candidate_name = st.text_input("Candidate Name", placeholder="e.g., Alice Johnson")
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True) # Spacer for vertical alignment
        if st.button("Add Candidate", use_container_width=True):
            if candidate_name:
                if add_candidate(candidate_name):
                    st.success(f"Candidate '{candidate_name}' added successfully.")
                    st.experimental_rerun()
                else:
                    st.error("Failed to add candidate.")
            else:
                st.warning("Please enter a candidate name.")

    st.markdown("---")
    st.subheader("📊 Live Voting Results")

    # Fetch and display results
    candidates, total_votes = get_candidates()

    if not candidates:
        st.write("No candidates registered yet.")
    else:
        st.metric(label="Total Votes Cast", value=total_votes)
        
        # Sort candidates by vote count descending
        sorted_candidates = sorted(candidates, key=lambda x: x['voteCount'], reverse=True)

        for candidate in sorted_candidates:
            count = candidate['voteCount']
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            
            st.markdown(f"**{candidate['name']}** ({count} votes)")
            st.progress(percentage / 100, text=f"{percentage:.1f}%")
