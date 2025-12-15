import streamlit as st
import pandas as pd
from voting_system import get_system
import pyperclip # Used for simple local copy

st.set_page_config(layout="wide", page_title="Private Key Portal")
system = get_system()

st.title("⚠️ Private Key Portal (Demonstration Use Only)")
st.warning("This view contains sensitive **Private Keys** and must be secured in a real-world scenario.")
st.divider()

# --- Security Gate (Simple for Demo) ---
# In a real app, this would be a proper login
password = st.text_input("Enter Demo Password to View Keys (Use 'admin')", type="password")

if password == "admin":
    st.header("Voter Credentials (Including Private Keys)")
    
    if not st.session_state.voters:
        st.info("No voters registered yet.")
    else:
        df_voters = pd.DataFrame(st.session_state.voters)
        
        st.subheader(f"Total Voters: {len(df_voters)}")
        
        # Structure the table for easy copying
        voters_data = []
        for i, row in df_voters.iterrows():
            # Create a unique key for each copy button
            copy_pub_key = f"copy_pub_{i}"
            copy_priv_key = f"copy_priv_{i}"

            # Create columns for keys and copy buttons
            cols = st.columns([1, 1, 1, 1])
            
            cols[0].markdown(f"**Name:** {row['name']}")
            cols[1].markdown(f"**DOB:** {row['dob']}")
            
            # Public Key and Copy Button
            cols[0].code(row['pub_key'][:15] + '...', language='text')
            if cols[0].button("📋 Copy Public Key", key=copy_pub_key):
                # Using st.code with a tiny font size for the actual key text
                pyperclip.copy(row['pub_key'])
                st.toast("Public Key copied!", icon="✅")

            # Private Key and Copy Button
            cols[1].code(row['priv_key'][:15] + '...', language='text')
            if cols[1].button("🔑 Copy Private Key", key=copy_priv_key):
                pyperclip.copy(row['priv_key'])
                st.toast("Private Key copied!", icon="✅")
                
            st.markdown("---")
            
else:
    st.error("Incorrect password.")
