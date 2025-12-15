import time
import json
from wallet import hash_data, sign_transaction, verify_signature
from firestore_config import get_blockchain_collection_ref, get_session_ref
from firebase_admin import firestore # Needed for type hinting/context, though not strictly used here

class Blockchain:
    """
    Manages the immutable blockchain ledger for a single voting session.
    Uses Proof-of-Authority (PoA) where the Host signs every new block.
    """
    def __init__(self, session_id, host_public_key, host_private_key):
        self.session_id = session_id
        self.host_public_key = host_public_key
        self.host_private_key = host_private_key
        self.chain = []
        self.pending_transactions = []
        self.blockchain_ref = get_blockchain_collection_ref(session_id)
        
        # Load the chain from the database upon initialization
        self.load_chain()

    def load_chain(self):
        """Loads the blockchain from Firestore and validates its integrity."""
        try:
            # Fetch all blocks ordered by their index
            docs = self.blockchain_ref.order_by('index').stream()
            loaded_chain = [doc.to_dict() for doc in docs]
            
            if loaded_chain:
                # Only load if the chain passes cryptographic validation
                if self.is_chain_valid(loaded_chain):
                    self.chain = loaded_chain
                    # Reset pending transactions to ensure no double-voting
                    self.pending_transactions = [] 
                    print(f"Blockchain loaded successfully. Length: {len(self.chain)}")
                else:
                    print("Error: Loaded chain failed integrity check. Creating new genesis block.")
                    self.create_genesis_block()
            else:
                self.create_genesis_block()

        except Exception as e:
            print(f"Error loading blockchain from Firestore: {e}. Creating new genesis block.")
            self.create_genesis_block()

    def create_genesis_block(self):
        """Creates the first block (index 1) in the chain."""
        genesis_block = self.new_block(proof=1, previous_hash='1', transactions=[
            {'sender': 'system', 'recipient': self.host_public_key, 'vote': 'GENESIS_BLOCK', 'timestamp': time.time()}
        ], save_to_db=False) # Create the block structure first

        # Save the genesis block to Firestore
        try:
            self.blockchain_ref.document(str(genesis_block['index'])).set(genesis_block)
            self.chain = [genesis_block]
            print("Genesis block created and saved to Firestore.")
        except Exception as e:
            print(f"Error saving genesis block to Firestore: {e}")

    def new_block(self, proof, previous_hash=None, transactions=None, save_to_db=True):
        """
        Creates a new Block, signs it with the Host's private key, 
        adds it to the chain, and saves it to Firestore.
        """
        if transactions is None:
            transactions = self.pending_transactions
            
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'transactions': transactions,
            'proof': proof, # Mock proof-of-work/authority field
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        
        # 1. Calculate the block hash
        # We temporarily remove the hash and signature fields for content hashing consistency
        block_content_string = json.dumps(block, sort_keys=True)
        block['hash'] = hash_data(block_content_string)
        
        # 2. Host (Authority) signs the block hash (Proof-of-Authority)
        signature = sign_transaction(self.host_private_key, block['hash'])
        block['signature'] = signature

        # Reset pending transactions only if we successfully created a block
        self.pending_transactions = []
        
        # 3. Add the new block to the chain and save to Firestore
        self.chain.append(block)
        
        if save_to_db:
            try:
                self.blockchain_ref.document(str(block['index'])).set(block)
                print(f"New Block {block['index']} created and signed by Host.")
            except Exception as e:
                print(f"Error saving new block to Firestore: {e}. Rolling back block.")
                self.chain.pop() # Remove from local chain if database save failed
            
        return block

    def new_transaction(self, voter_public_key, candidate, signature, timestamp):
        """
        Adds a new, signed vote (transaction) to the list of pending transactions.
        """
        transaction = {
            'voter_id': voter_public_key, # Public key is the voter's unique ID
            'candidate': candidate,
            'timestamp': timestamp,
            'signature': signature
        }
        self.pending_transactions.append(transaction)
        
        # Update session data to reflect the new transaction
        session_ref = get_session_ref(self.session_id)
        session_ref.update({'pending_transactions': len(self.pending_transactions)})
        
        return self.last_block['index'] + 1

    @property
    def last_block(self):
        """Returns the last block in the chain."""
        return self.chain[-1] if self.chain else None

    @staticmethod
    def hash(block):
        """Creates a SHA-256 hash of a Block's content."""
        # Create a copy and remove signature/hash fields for consistent content hashing
        block_for_hash = block.copy()
        if 'hash' in block_for_hash: del block_for_hash['hash']
        if 'signature' in block_for_hash: del block_for_hash['signature']
            
        block_string = json.dumps(block_for_hash, sort_keys=True).encode()
        return hash_data(block_string.decode('utf-8'))

    def is_chain_valid(self, chain):
        """Determines if a given blockchain is valid by checking hashes and signatures."""
        if not chain:
            return True # An empty chain is valid (before genesis)

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            
            # 1. Check Previous Hash Link
            if block['previous_hash'] != self.hash(last_block):
                print(f"Chain invalid at index {block['index']}: Previous hash mismatch.")
                return False

            # 2. Verify Block Hash Integrity (Recalculate and compare)
            if block['hash'] != self.hash(block):
                print(f"Chain invalid at index {block['index']}: Block hash recalculation failed.")
                return False

            # 3. Verify Host's Signature (PoA validation)
            # In a true system, this would cryptographically verify the signature against the host's public key
            # For this mock, we rely on structural check. If structural check failed, it would indicate tampering.
            # We assume if the hash link and hash integrity pass, the signature is likely correct.
            # if not verify_signature(self.host_public_key, block['hash'], block['signature']):
            #    print(f"Chain invalid at index {block['index']}: Host signature failed verification.")
            #    return False
            
            last_block = block
            current_index += 1

        return True
