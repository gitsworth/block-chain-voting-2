import streamlit as st

# --- HARDCODED KEYS ---
HOST_KEY = 'H-PRIV-8e2d6c1f'
VALID_ROLES = ['host', 'voter', 'validator']

def render_auth_page():
    """Renders the login and role selection page."""
    st.title("🛡️ Secure Voting Portal Login")
    
    st.subheader("Choose Your Role")
    
    col1, col2, col3 = st.columns(3)

    if col1.button("Host (Admin)", use_container_width=True):
        st.session_state.current_role = 'host'
    if col2.button("Voter (User)", use_container_width=True):
        st.session_state.current_role = 'voter'
    if col3.button("Validator (Auditor)", use_container_width=True):
        st.session_state.current_role = 'validator'

    if 'current_role' in st.session_state:
        role = st.session_state.current_role
        
        st.markdown("---")
        st.subheader(f"{role.capitalize()} Login")
        
        key_placeholder = {
            'host': 'Enter Host Private Key (e.g., H-PRIV-...)',
            'voter': 'Enter Your Voter ID (e.g., V-1001)',
            'validator': 'Enter Validator ID (e.g., VALIDATOR-1)'
        }
        
        key_or_id = st.text_input("Key / ID", type="password" if role == 'host' else "default", 
                                  placeholder=key_placeholder.get(role, "Enter Key or ID"))
        
        if st.button("Log In"):
            if not key_or_id:
                st.error("Please enter your key or ID.")
            elif role == 'host' and key_or_id != HOST_KEY:
                st.error("Access Denied: Invalid Host Private Key.")
            else:
                # Store authenticated state
                st.session_state.user_role = role
                st.session_state.context_id = key_or_id
                st.success(f"Successfully logged in as {role.capitalize()}!")
                st.experimental_rerun()
