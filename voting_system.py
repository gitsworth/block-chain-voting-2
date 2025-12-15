import hashlib
import json
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import base64

# --- Constants ---
MAX_CANDIDATES = 10
MAX_VOTERS = 100
MIN_VOTING_AGE = 18

# --- Utility Functions for Keys and Hashing ---

def generate_key_pair():
    """Generates a new RSA private and public key pair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    
    # Serialize keys for storage and display
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_pem, public_pem

def encrypt_vote(public_key_pem: str, candidate_name: str) -> str:
    """Encrypts the candidate name using the voter's public key."""
    # Load the public key
    public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    
    # Encrypt the candidate name
    encrypted_data = public_key.encrypt(
        candidate_name.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return base64.b64encode(encrypted_data).decode('utf-8')

def decrypt_vote(private_key_pem: str, encrypted_vote_b64: str) -> str:
    """Decrypts the candidate name using the corresponding private key."""
    try:
        # Load the private key
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None
        )
        encrypted_data = base64.b64decode(encrypted_vote_b64.encode('utf-8'))
        
        # Decrypt the data
        decrypted_data = private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return decrypted_data.decode('utf-8')
    except Exception as e:
        return f"DECRYPTION_ERROR: {e}" # Should only be used by Host to tally

def hash_data(data: str) -> str:
    """Returns the SHA-256 hash of a string."""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

# --- Blockchain Class ---

class Block:
    """Represents a single block in the blockchain (a single, anonymous vote)."""
    def __init__(self, index, timestamp, data, previous_hash):
        self.index = index
        self.timestamp = timestamp
        self.data = data # Contains encrypted_vote and public_key_hash
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        """Calculates the hash of the block content."""
        block_string = json.dumps(self.__dict__, sort_keys=True)
        return hash_data(block_string)

class Blockchain:
    """Manages the chain of blocks (votes)."""
    def __init__(self):
        self.chain = []
        self.create_genesis_block()

    def create_genesis_block(self):
        """Creates the first block in the chain."""
        self.chain.append(Block(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Genesis Block", "0"))

    @property
    def last_block(self):
        """Returns the last block in the chain."""
        return self.chain[-1]

    def add_block(self, voter_pub_key_hash, encrypted_vote):
        """Adds a new block (vote) to the chain."""
        index = len(self.chain)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Anonymized data for the block
        data = {
            'voter_pub_key_hash': voter_pub_key_hash,
            'encrypted_vote': encrypted_vote
        }
        
        new_block = Block(index, timestamp, data, self.last_block.hash)
        self.chain.append(new_block)
        return new_block

# --- State Manager ---

class VotingSystem:
    """Central manager for the entire application state."""
    def __init__(self):
        self._initialize_state()

    def _initialize_state(self):
        """Sets up initial values for Streamlit session_state."""
        import streamlit as st
        
        # Core data structures
        if 'candidates' not in st.session_state:
            st.session_state.candidates = [] # [{'name': 'C1', 'votes': 0}]
        if 'voters' not in st.session_state:
            st.session_state.voters = [] # [{'name': 'John', 'dob': '...', 'pub_key': '...', 'priv_key': '...', 'has_voted': False}]
        if 'blockchain' not in st.session_state:
            st.session_state.blockchain = Blockchain()

        # Phase control
        if 'election_phase' not in st.session_state:
            st.session_state.election_phase = 'registration' # 'registration', 'voting', 'ended'

        # Candidate names for case-insensitive check
        if 'candidate_names_lower' not in st.session_state:
             st.session_state.candidate_names_lower = set()
    
    # --- Candidate Management ---

    def add_candidate(self, name: str) -> str:
        """Adds a candidate if conditions are met."""
        if st.session_state.election_phase != 'registration':
            return "Cannot add candidates after registration has ended."
        if len(st.session_state.candidates) >= MAX_CANDIDATES:
            return f"Maximum of {MAX_CANDIDATES} candidates reached."
        if name.lower() in st.session_state.candidate_names_lower:
            return "Candidate name must be unique (case-insensitive)."
        
        st.session_state.candidates.append({'name': name, 'votes': 0})
        st.session_state.candidate_names_lower.add(name.lower())
        return f"Candidate '{name}' added successfully."

    def remove_candidate(self, name: str):
        """Removes a candidate."""
        st.session_state.candidates = [c for c in st.session_state.candidates if c['name'] != name]
        st.session_state.candidate_names_lower.discard(name.lower())

    # --- Voter Management ---

    def register_voter(self, name: str, dob: datetime) -> tuple[bool, str]:
        """Registers a new voter."""
        if st.session_state.election_phase != 'registration':
            return False, "Registration is closed."
        if len(st.session_state.voters) >= MAX_VOTERS:
            return False, f"Maximum of {MAX_VOTERS} voters registered."
        
        # Check eligibility (age)
        age = relativedelta(datetime.now(), dob).years
        if age < MIN_VOTING_AGE:
            return False, f"Ineligible: Voter must be {MIN_VOTING_AGE} years or older. Current age is {age}."

        # Check for unique (Name + DOB) combination
        dob_str = dob.strftime("%Y-%m-%d")
        if any(v['name'].lower() == name.lower() and v['dob'] == dob_str for v in st.session_state.voters):
            return False, "Registration failed: A voter with the same Name and Date of Birth already exists."

        # Generate keys and register
        private_key_pem, public_key_pem = generate_key_pair()
        
        voter_data = {
            'name': name,
            'dob': dob_str,
            'pub_key': public_key_pem,
            'priv_key': private_key_pem,
            'has_voted': False
        }
        st.session_state.voters.append(voter_data)
        
        return True, "Registration successful."

    def remove_voter(self, dob_str: str, pub_key: str):
        """Removes a voter from the voterbase."""
        st.session_state.voters = [
            v for v in st.session_state.voters 
            if not (v['dob'] == dob_str and v['pub_key'] == pub_key)
        ]

    def authenticate_and_vote(self, name: str, dob: str, pub_key: str, priv_key: str, candidate_name: str) -> tuple[bool, str]:
        """Authenticates a voter and casts the vote."""
        if st.session_state.election_phase != 'voting':
            return False, "Voting is not currently active."
        
        # 1. Authenticate Voter
        voter_record = next((v for v in st.session_state.voters 
                             if v['name'].lower() == name.lower() and 
                                v['dob'] == dob and
                                v['pub_key'] == pub_key and
                                v['priv_key'] == priv_key), None)
        
        if not voter_record:
            return False, "Authentication failed: Credentials do not match a registered voter."

        # 2. Check for Double Vote
        if voter_record['has_voted']:
            return False, "Double vote detected: This voter has already cast their ballot."

        # 3. Encrypt Vote
        try:
            encrypted_vote = encrypt_vote(pub_key, candidate_name)
        except Exception as e:
            return False, f"Vote encryption failed: {e}"

        # 4. Create Anonymized Block (Voter identity is now obscured)
        voter_pub_key_hash = hash_data(pub_key)
        st.session_state.blockchain.add_block(voter_pub_key_hash, encrypted_vote)
        
        # 5. Mark Voter as Voted
        for v in st.session_state.voters:
            if v['pub_key'] == pub_key:
                v['has_voted'] = True
                break
        
        return True, "Vote successfully cast and added to the blockchain."

    # --- Phase Control ---

    def start_vote(self) -> str:
        """Transitions the phase from registration to voting."""
        if st.session_state.election_phase == 'voting':
            return "Voting has already started."
        if st.session_state.election_phase == 'ended':
            return "The election has already ended."

        # Clear any candidates added in the host portal that might have failed to save (optional cleanup)
        st.session_state.election_phase = 'voting'
        return "Registration closed. Voting started successfully."

    def end_vote(self) -> str:
        """Transitions the phase from voting to ended."""
        if st.session_state.election_phase == 'registration':
            return "Cannot end vote: Voting has not yet started."
        if st.session_state.election_phase == 'ended':
            return "The election has already ended."
        
        # Tally the results before ending
        self._tally_results()
        
        st.session_state.election_phase = 'ended'
        return "Voting ended successfully. Results are now available."

    # --- Results Tally ---

    def _tally_results(self):
        """Decrypts and tallies votes from the blockchain."""
        
        # Find all private keys for decryption
        private_keys = {hash_data(v['pub_key']): v['priv_key'] for v in st.session_state.voters}
        
        tally = {c['name']: 0 for c in st.session_state.candidates}
        
        for block in st.session_state.blockchain.chain[1:]: # Skip Genesis block
            pub_hash = block.data['voter_pub_key_hash']
            encrypted_vote = block.data['encrypted_vote']
            
            # Use the private key corresponding to the public key hash to decrypt
            if pub_hash in private_keys:
                candidate_name = decrypt_vote(private_keys[pub_hash], encrypted_vote)
                
                # Update tally if decryption was successful and candidate exists
                if not candidate_name.startswith("DECRYPTION_ERROR") and candidate_name in tally:
                    tally[candidate_name] += 1
            else:
                # Should not happen in a correctly running system
                print(f"ERROR: Private key not found for hash {pub_hash}")
        
        # Update the candidates list with final vote counts
        for candidate in st.session_state.candidates:
            candidate['votes'] = tally.get(candidate['name'], 0)

# --- Initializer for Streamlit App ---

def get_system() -> VotingSystem:
    """Initializes and returns the VotingSystem instance."""
    import streamlit as st
    if 'voting_system' not in st.session_state:
        st.session_state.voting_system = VotingSystem()
    return st.session_state.voting_system
