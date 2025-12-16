# firestore_config.py - Firebase initialization and database path definitions
from google.cloud import firestore
import json
import os

# --- MANDATORY GLOBAL VARIABLES from Canvas Environment ---
# Ensure these variables are available (simulating the environment injection)
# In a Streamlit environment, these are usually handled by the underlying execution context.
try:
    # The environment provides __firebase_config and __app_id
    FIREBASE_CONFIG_JSON = os.environ.get('__firebase_config', '{}')
    FIREBASE_CONFIG = json.loads(FIREBASE_CONFIG_JSON)
    APP_ID = os.environ.get('__app_id', 'default-app-id')
except:
    # Fallback for local testing outside the environment
    FIREBASE_CONFIG = {}
    APP_ID = 'default-app-id'

# --- 1. Firestore Client Initialization ---
# We use the google.cloud.firestore client for Python applications.

# Attempt to initialize Firestore, handle case where config is empty
try:
    if 'projectId' in FIREBASE_CONFIG:
        db = firestore.Client(project=FIREBASE_CONFIG['projectId'])
    else:
        # Fallback if running outside a properly configured environment
        print("WARNING: Firestore project ID not found in config. Using default client.")
        db = firestore.Client() 
except Exception as e:
    print(f"ERROR initializing Firestore client: {e}")
    # Create a mock object if initialization fails critically
    db = None 

# --- 2. Core Path Definitions ---

# Define a single, fixed session ID for this demo
SINGLE_SESSION_ID = "main_election_2025"

# --- Public Data Paths (Session Metadata, Blockchain Ledger) ---

# The collection for storing the single active session metadata
SESSION_COLLECTION_PATH = f"artifacts/{APP_ID}/public/data/voting_session"
# The specific document ID for the session metadata
SESSION_DOC_ID = "current_session" 

# The collection base path for the actual blockchain blocks
BLOCKCHAIN_COLLECTION_PATH_BASE = f"artifacts/{APP_ID}/public/data/blockchain"
# The collection for storing voter PII and keys (Host-accessible for registration/management)
VOTERS_COLLECTION_PATH = f"artifacts/{APP_ID}/public/data/voters" 


# --- 3. Reference Helper Functions ---

def get_session_ref():
    """Returns the DocumentReference for the single active election session."""
    if db is None:
        raise Exception("Firestore client is not initialized.")
    return db.collection(SESSION_COLLECTION_PATH).document(SESSION_DOC_ID)

def get_voters_collection_ref():
    """Returns the CollectionReference for the list of registered voters."""
    if db is None:
        raise Exception("Firestore client is not initialized.")
    return db.collection(VOTERS_COLLECTION_PATH)

def get_blockchain_collection_ref(session_id=SINGLE_SESSION_ID):
    """Returns the CollectionReference for the blockchain blocks specific to the session."""
    if db is None:
        raise Exception("Firestore client is not initialized.")
    # The path is: artifacts/{APP_ID}/public/data/blockchain/{session_id}/blocks
    return db.collection(BLOCKCHAIN_COLLECTION_PATH_BASE).document(session_id).collection('blocks')
