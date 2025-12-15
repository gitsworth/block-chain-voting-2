import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import json

# --- Global Configuration Variables ---
# MANDATORY: These variables are provided by the Canvas environment.
appId = "default-app-id" # Fallback if not defined
firebaseConfig = {}
initialAuthToken = None

# Check for environment variables and ensure initialization happens once
if 'st.session_state.db' not in st.session_state:
    if hasattr(st, '__app_id'):
        appId = st.__app_id
    
    if hasattr(st, '__firebase_config'):
        try:
            # Parse the configuration string provided by the environment
            firebaseConfig = json.loads(st.__firebase_config)
        except json.JSONDecodeError:
            st.error("Fatal Error: __firebase_config is not valid JSON.")
            st.stop()
    else:
        st.error("Fatal Error: __firebase_config environment variable is missing.")
        st.stop()
        
    if hasattr(st, '__initial_auth_token'):
        initialAuthToken = st.__initial_auth_token

    # --- Initialize Firebase and Authentication ---
    try:
        if not firebase_admin._apps:
            # This line requires the JSON content of a Firebase Service Account key file.
            # The error 'Certificate must contain a "type" field set to "service_account"'
            # means the 'firebaseConfig' dictionary does not have this field.
            cred = credentials.Certificate(firebaseConfig)
            firebase_admin.initialize_app(cred, name=appId)
        
        db = firestore.client(app=firebase_admin.get_app(appId))
        
        # We use the app ID as a pseudo-user ID for the centralized host system
        user_id = appId 
        
        st.session_state.db = db
        st.session_state.user_id = user_id
        
        print("Firebase initialized successfully.")
    except Exception as e:
        st.error(f"Failed to initialize Firebase: {e}")
        st.stop()

# --- Firestore Reference Builders ---

def get_session_ref(session_id):
    """Returns the Firestore document reference for a specific voting session."""
    # Collection path: /artifacts/{appId}/users/{userId}/voting_sessions/{sessionId}
    return st.session_state.db.collection(
        u'artifacts').document(st.session_state.user_id
        ).collection(u'voting_sessions').document(session_id)

def get_voters_collection_ref(session_id):
    """Returns the Firestore collection reference for all voters in a session."""
    # Voter collection path: /artifacts/{appId}/users/{userId}/voting_sessions/{sessionId}/voters
    return get_session_ref(session_id).collection(u'voters')

def get_blockchain_collection_ref(session_id):
    """Returns the Firestore collection reference for the blockchain in a session."""
    # Blockchain collection path: /artifacts/{appId}/users/{userId}/voting_sessions/{sessionId}/blockchain
    return get_session_ref(session_id).collection(u'blockchain')

def get_all_sessions_ref():
    """Returns the Firestore collection reference for all voting sessions."""
    # All sessions collection path: /artifacts/{appId}/users/{userId}/voting_sessions
    return st.session_state.db.collection(
        u'artifacts').document(st.session_state.user_id
        ).collection(u'voting_sessions')
