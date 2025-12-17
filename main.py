# main.py
import streamlit as st
from auth_page import render_auth_page
from host_portal import render_host_portal
from validator_portal import render_validator_portal
from voter_portal import render_voter_portal

# Define the page configurations
st.set_page_config(
    page_title="Decentralized Voting System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Streamlit session state variables if they don't exist
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None

# -----------------
# Main Application Flow
# -----------------

def main():
    """
    Renders the appropriate application portal based on the user's login state and role.
    """
    st.sidebar.title("Decentralized Voting App")

    # If the user is NOT logged in, show the authentication page
    if not st.session_state['logged_in']:
        st.sidebar.info("Please log in or select a role to proceed.")
        render_auth_page()
    else:
        # User is logged in, show the appropriate portal based on role
        st.sidebar.header(f"Logged in as: {st.session_state['user_role']}")
        st.sidebar.text(f"User ID: {st.session_state['user_id']}")

        # Navigation and Logout Button
        if st.sidebar.button("Logout", key="logout_btn"):
            st.session_state['logged_in'] = False
            st.session_state['user_role'] = None
            st.session_state['user_id'] = None
            st.rerun() # Rerun to switch back to the auth page

        # Render the specific portal
        role = st.session_state['user_role']
        st.subheader(f"Welcome to the {role} Portal")

        if role == "Host":
            render_host_portal()
        elif role == "Voter":
            render_voter_portal()
        elif role == "Validator":
            render_validator_portal()
        else:
            # Should not happen if roles are managed correctly
            st.error("Invalid user role. Please log out and try again.")
            
if __name__ == "__main__":
    main()
