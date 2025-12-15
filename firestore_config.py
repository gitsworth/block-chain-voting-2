import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import json
import warnings

# Suppress warnings from firebase_admin if it's run without proper credentials
warnings.filterwarnings("ignore", category=UserWarning, module='firebase_admin')

# --- Global Configuration Variables ---
# MANDATORY: These variables are provided by the Canvas environment.
appId = "default-app-id" # Fallback if not defined
firebaseConfig = {}
initialAuthToken = None
is_firestore_enabled = False

# Check for environment variables and ensure initialization happens once
if 'st.session_state.db' not in st.session_state:
    
    # Check for environment variables
    has_app_id = hasattr(st, '__app_id')
    has_firebase_config = hasattr(st, '__firebase_config')
    
    if has_app_id:
        appId = st.__app_id
        
    if has_firebase_config:
        try:
            # Parse the configuration string provided by the environment
            firebaseConfig = json.loads(st.__firebase_config)
            is_firestore_enabled = True
        except json.JSONDecodeError:
            st.error("Fatal Error: __firebase_config is not valid JSON.")
            st.stop()
    
    if hasattr(st, '__initial_auth_token'):
        initialAuthToken = st.__initial_auth_token

    # --- Initialize Firebase or Mock DB ---
    try:
        if is_firestore_enabled:
            # 1. Real Firestore Initialization (Requires Service Account JSON)
            if not firebase_admin._apps:
                # If this fails, it often means the provided JSON (firebaseConfig) 
                # is the client config, not the Service Account JSON.
                cred = credentials.Certificate(firebaseConfig)
                firebase_admin.initialize_app(cred, name=appId)
            
            db = firestore.client(app=firebase_admin.get_app(appId))
            user_id = appId # Centralized host system ID
            st.session_state.db = db
            st.session_state.user_id = user_id
            print("Real Firestore client initialized successfully.")
            
        else:
            # 2. Mock DB Fallback (For local running outside Canvas)
            st.warning("⚠️ Environment variables are missing. Firestore connectivity is disabled. Using a Mock DB. Persistence and multi-user features will NOT work.")
            
            # Define simple mock objects that allow subsequent code to call .collection().document().set() without crashing
            class MockDocument:
                def __init__(self, doc_id):
                    self.doc_id = doc_id
                def set(self, data): print(f"MOCK DB: Setting document {self.doc_id}")
                def get(self): return self
                def to_dict(self): return None # Returns None to simulate doc not found
                def update(self, data): print(f"MOCK DB: Updating document {self.doc_id}")
            
            class MockCollection:
                def document(self, doc_id): return MockDocument(doc_id)
                def stream(self): return []
                def order_by(self, field): return self
                def where(self, field, op, value): return self
            
            class MockDB:
                def collection(self, name): return MockCollection()
            
            st.session_state.db = MockDB()
            st.session_state.user_id = "mock_user_id"
            
    except Exception as e:
        st.error(f"Failed to initialize Firebase: {e}. Check if __firebase_config is the correct Service Account JSON.")
        st.stop()

# --- Firestore Reference Builders (Use st.session_state.db which is now guaranteed to exist) ---

def get_session_ref(session_id):
    """Returns the Firestore document reference for a specific voting session."""
    return st.session_state.db.collection(
        u'artifacts').document(st.session_state.user_id
        ).collection(u'voting_sessions').document(session_id)

def get_voters_collection_ref(session_id):
    """Returns the Firestore collection reference for all voters in a session."""
    return get_session_ref(session_id).collection(u'voters')

def get_blockchain_collection_ref(session_id):
    """Returns the Firestore collection reference for the blockchain in a session."""
    return get_session_ref(session_id).collection(u'blockchain')

def get_all_sessions_ref():
    """Returns the Firestore collection reference for all voting sessions."""
    return st.session_state.db.collection(
        u'artifacts').document(st.session_state.user_id
        ).collection(u'voting_sessions')
