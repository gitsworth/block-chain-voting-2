import streamlit as st
import json
import hashlib
from firebase_admin import initialize_app, firestore, credentials

# --- Global Configuration (Emulating Canvas Environment Vars) ---
# NOTE: In a real-world Streamlit deployment, these variables should be securely
# retrieved from environment variables or Streamlit secrets, not hardcoded.
try:
    APP_ID = st.secrets.get('app_id', 'voting-app-default')
    FIREBASE_CONFIG_JSON = st.secrets.get('firebase_config', '{}')
    FIREBASE_CONFIG = json.loads(FIREBASE_CONFIG_JSON)
except Exception:
    # Fallback for local testing if secrets are not set
    APP_ID = 'voting-app-default'
    FIREBASE_CONFIG = {}

# --- Firestore Paths ---
CANDIDATES_COLLECTION = f"artifacts/{APP_ID}/public/data/candidates"
VOTES_COLLECTION = f"artifacts/{APP_ID}/public/data/votes"
BLOCKCHAIN_COLLECTION = f"artifacts/{APP_ID}/public/data/blockchain"
LEDGER_DOC_PATH = f"{BLOCKCHAIN_COLLECTION}/ledger"

def init_firestore():
    """Initializes Firebase Admin SDK and returns the Firestore client."""
    if not FIREBASE_CONFIG:
        st.error("Firebase configuration is missing. Cannot initialize database.")
        return None

    try:
        # Check if the app is already initialized
        if not initialize_app():
            # Use the config to create a credentials object.
            # In a secure environment, this JSON should contain the service account key.
            # Assuming the provided config is sufficient for simple use or uses local credentials.
            # Since Canvas provides initial auth token, the admin SDK setup is slightly different.
            # For server-side Python (Streamlit), we typically need a service account JSON.
            
            # Since we don't have the service account JSON, we will try to initialize
            # with default application credentials if available, otherwise, we'll use a placeholder.
            
            # In a real Streamlit deployment, you'd load your service account JSON file
            # or pass the JSON content via secrets.
            
            # Placeholder initialization (may fail without proper credentials):
            initialize_app(options={'projectId': FIREBASE_CONFIG.get('projectId')})

        return firestore.client()
    except ValueError:
        # Already initialized
        return firestore.client()
    except Exception as e:
        st.error(f"Error initializing Firebase Admin SDK: {e}")
        return None

def get_db():
    """Returns the Firestore client, initializing it if necessary."""
    if 'db' not in st.session_state:
        st.session_state.db = init_firestore()
    return st.session_state.db

# --- Firestore Operations ---

def get_candidates():
    """Fetches all candidates and calculates total votes."""
    db = get_db()
    if not db: return [], 0

    try:
        candidates_ref = db.collection(CANDIDATES_COLLECTION)
        candidates_data = []
        total_votes = 0
        for doc in candidates_ref.stream():
            data = doc.to_dict()
            # Calculate total vote count based on the arrayUnion structure (list of 1s)
            count = len(data.get('voteCount', []))
            total_votes += count
            candidates_data.append({'id': doc.id, 'name': data['name'], 'voteCount': count})
        return candidates_data, total_votes
    except Exception as e:
        st.error(f"Error fetching candidates: {e}")
        return [], 0

def add_candidate(name):
    """Adds a new candidate to the database."""
    db = get_db()
    if not db: return False

    try:
        candidates_ref = db.collection(CANDIDATES_COLLECTION)
        candidates_ref.add({
            'name': name,
            'voteCount': [],  # Use array for tracking votes to enable atomic updates
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        st.error(f"Error adding candidate: {e}")
        return False

def check_voter_voted(voter_id):
    """Checks if a given voter ID has already cast a vote."""
    db = get_db()
    if not db: return True # Fail safe

    try:
        votes_ref = db.collection(VOTES_COLLECTION)
        query = votes_ref.where('voterId', '==', voter_id).limit(1).get()
        return len(query) > 0
    except Exception as e:
        st.error(f"Error checking voter status: {e}")
        return True # Assume voted if error

def record_vote_document(voter_id, candidate_id, candidate_name):
    """Records the vote document and returns its ID."""
    db = get_db()
    if not db: return None

    try:
        votes_ref = db.collection(VOTES_COLLECTION)
        doc_ref = votes_ref.add({
            'voterId': voter_id,
            'candidateId': candidate_id,
            'candidateName': candidate_name,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'blockMined': False
        })
        return doc_ref[1].id # Returns the ID of the new document
    except Exception as e:
        st.error(f"Error recording vote document: {e}")
        return None

def update_candidate_vote_count(candidate_id, vote_amount=1):
    """Atomically updates a candidate's vote count after block mining."""
    db = get_db()
    if not db: return False

    try:
        candidate_ref = db.collection(CANDIDATES_COLLECTION).document(candidate_id)
        candidate_ref.update({
            'voteCount': firestore.ArrayUnion([vote_amount])
        })
        return True
    except Exception as e:
        st.error(f"Error updating candidate vote count: {e}")
        return False

def mark_vote_mined(vote_doc_id):
    """Marks a vote document as processed by the blockchain."""
    db = get_db()
    if not db: return False
    
    try:
        vote_ref = db.collection(VOTES_COLLECTION).document(vote_doc_id)
        vote_ref.update({'blockMined': True})
        return True
    except Exception as e:
        st.error(f"Error marking vote as mined: {e}")
        return False

def get_ledger():
    """Loads the blockchain state (chain and pending transactions) from Firestore."""
    db = get_db()
    if not db: return None

    try:
        doc = db.document(LEDGER_DOC_PATH).get()
        if doc.exists:
            data = doc.to_dict()
            return data.get('chain', []), data.get('pendingTransactions', [])
        return [], []
    except Exception as e:
        st.error(f"Error retrieving ledger: {e}")
        return [], []

def save_ledger(chain, pending_transactions):
    """Saves the blockchain state to Firestore."""
    db = get_db()
    if not db: return False

    try:
        db.document(LEDGER_DOC_PATH).set({
            'chain': chain[-20:], # Save last 20 blocks
            'pendingTransactions': pending_transactions[:50] # Save last 50 transactions
        })
        return True
    except Exception as e:
        st.error(f"Error saving ledger: {e}")
        return False

def get_unmined_votes():
    """Fetches votes that have been recorded but not yet mined."""
    db = get_db()
    if not db: return []

    try:
        votes_ref = db.collection(VOTES_COLLECTION)
        query_results = votes_ref.where('blockMined', '==', False).limit(50).get()
        unmined_votes = [{'id': doc.id, **doc.to_dict()} for doc in query_results]
        return unmined_votes
    except Exception as e:
        st.error(f"Error fetching unmined votes: {e}")
        return []
