# blockchain.py - Defines the Block and Blockchain classes for ledger management.
import json
import time
from firestore_config import db, get_blockchain_collection_ref, get_session_ref
from wallet import hash_data, sign_data, verify_signature

# --- 1. Block Data Structure ---

class Block:
    """Represents a single block in the blockchain ledger."""
    
    def __init__(self, index, timestamp, transactions, previous_hash, host_public_key, host_signature=None, nonce=0):
        """
        Initializes a new Block.
        
        Args:
            index (int): The position of the block in the chain (0 for genesis).
            timestamp (float): The time of block creation.
            transactions (list): List of verified vote transactions.
            previous_hash (str): Hash of the preceding block.
            host_public_key (str): Public key of the Host Authority who mined/signed the block.
            host_signature (str, optional): Digital signature of the Host Authority.
            nonce (int): Placeholder for Proof-of-Work, kept at 0 for Proof-of-Authority.
        """
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.host_public_key = host_public_key
        self.host_signature = host_signature
        self.nonce = nonce
        self.hash = self.compute_hash() # Hash is computed upon creation

    def compute_hash(self):
        """
        Calculates the SHA256 hash for the block content. 
        Note: The signature itself is NOT included in the hash, only the content is hashed.
        """
        # We need a deterministic representation of the block data
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            # Sorting transactions ensures consistent hash regardless of internal order
            "transactions": sorted(self.transactions, key=lambda tx: tx['signature']), 
            "previous_hash": self.previous_hash,
            "host_public_key": self.host_public_key,
            "nonce": self.nonce
        }, sort_keys=True)
        return hash_data(block_string)

    def to_dict(self):
        """Converts the Block object to a dictionary for Firestore storage."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "host_public_key": self.host_public_key,
            "host_signature": self.host_signature,
            "nonce": self.nonce
        }
    
    @classmethod
    def from_dict(cls, data):
        """Creates a Block object from a Firestore dictionary."""
        # Note: We pass the stored hash and signature, but recalculate the hash using compute_hash later for verification
        return cls(
            index=data.get('index'),
            timestamp=data.get('timestamp'),
            transactions=data.get('transactions', []),
            previous_hash=data.get('previous_hash'),
            host_public_key=data.get('host_public_key'),
            host_signature=data.get('host_signature'),
            nonce=data.get('nonce', 0)
        )

# --- 2. Blockchain Management ---

class Blockchain:
    """Manages the creation, persistence, and integrity of the blockchain."""
    
    def __init__(self, session_id, host_public_key, host_private_key=None):
        self.session_id = session_id
        self.host_public_key = host_public_key
        self.host_private_key = host_private_key # Required for mining/signing
        self.pending_transactions = []
        self.chain_ref = get_blockchain_collection_ref(session_id)
        
    def _get_last_block(self):
        """Retrieves the block with the highest index from Firestore (the latest block)."""
        try:
            # Query for the block with the maximum index
            query = self.chain_ref.order_by("index", direction=firestore.Query.DESCENDING).limit(1)
            results = list(query.stream())
            if results:
                return Block.from_dict(results[0].to_dict())
            return None # Chain is empty
        except Exception as e:
            print(f"Error retrieving last block: {e}")
            return None

    def _add_block_to_firestore(self, block):
        """Saves a new block to the Firestore collection."""
        try:
            # Firestore document ID is the block index
            block_doc_ref = self.chain_ref.document(str(block.index))
            block_doc_ref.set(block.to_dict())
            return True
        except Exception as e:
            print(f"Error saving block to Firestore: {e}")
            return False

    def initialize_blockchain(self):
        """Creates the genesis block if the chain does not exist."""
        if self._get_last_block() is None:
            # Create the genesis block (index 0, no transactions, previous_hash = '0')
            genesis_block = self._create_genesis_block()
            
            if self._add_block_to_firestore(genesis_block):
                print("Genesis block successfully created and saved.")
                return True
            else:
                print("Failed to save genesis block to Firestore.")
                return False
        return False # Chain already exists
        
    def _create_genesis_block(self):
        """Creates the very first block in the chain."""
        # The data that the Host signs
        genesis_data = json.dumps({
            "index": 0,
            "timestamp": time.time(),
            "transactions": [],
            "previous_hash": "0",
            "host_public_key": self.host_public_key,
            "nonce": 0
        }, sort_keys=True)
        
        # Create a temporary block object to get the hash for signing
        genesis = Block(0, time.time(), [], "0", self.host_public_key, nonce=0)
        block_hash = genesis.compute_hash()
        
        # Host signs the hash of the genesis block data
        host_signature = sign_data(self.host_private_key, block_hash)
        
        # Final block object with the signature
        genesis.host_signature = host_signature
        
        return genesis

    def add_transaction(self, voter_id, candidate, signature):
        """Adds a new vote transaction to the pending list."""
        
        # The transaction data itself is the signed vote + its components
        transaction = {
            'voter_id': voter_id,
            'candidate': candidate,
            'timestamp': time.time(),
            'signature': signature # Voter's signature on the vote
        }
        self.pending_transactions.append(transaction)
        
        # Update session document to reflect pending transactions
        try:
            session_ref = get_session_ref()
            session_ref.update({
                'pending_transactions': len(self.pending_transactions),
                'pending_transactions_list': self.pending_transactions
            })
        except Exception as e:
            print(f"Warning: Failed to update session pending transactions count: {e}")

    def new_block(self, proof):
        """
        Mines a new block, including all pending transactions.
        (PoA: Proof is a placeholder, actual authority is the Host's signature).
        """
        last_block = self._get_last_block()
        if not last_block:
            raise Exception("Cannot mine: Blockchain not initialized (No Genesis Block).")
            
        # Create the new block object
        new_index = last_block.index + 1
        new_block = Block(
            index=new_index,
            timestamp=time.time(),
            transactions=list(self.pending_transactions), # Copy the list
            previous_hash=last_block.hash,
            host_public_key=self.host_public_key,
            nonce=proof # Placeholder for PoA
        )
        
        # --- Proof-of-Authority: Host Signs the Block ---
        block_hash_to_sign = new_block.compute_hash()
        
        if not self.host_private_key:
            raise Exception("Host Private Key is required to sign and mine the block (PoA).")
            
        # Host digitally signs the new block's content hash
        host_signature = sign_data(self.host_private_key, block_hash_to_sign)
        new_block.host_signature = host_signature
        
        # Add to Firestore and update session counts
        if self._add_block_to_firestore(new_block):
            
            # Clear pending transactions and update session metrics
            mined_count = len(self.pending_transactions)
            self.pending_transactions = []
            
            session_ref = get_session_ref()
            session_ref.update({
                'pending_transactions': 0,
                'pending_transactions_list': [],
                # Increment total votes by the number of transactions just mined
                'total_votes': firestore.Increment(mined_count)
            })
            
            return new_block.to_dict()
        else:
            raise Exception("Failed to save the new block to the ledger.")

    def is_chain_valid(self, chain_data):
        """
        Checks if the entire chain is valid by verifying hash links and Host signatures.
        
        Args:
            chain_data (list): A list of block dictionaries loaded from Firestore.
            
        Returns:
            bool: True if valid, False otherwise.
        """
        if not chain_data:
            return True # An empty chain (only possible before genesis) is technically valid
            
        previous_block = None
        for i, block_data in enumerate(chain_data):
            current_block = Block.from_dict(block_data)

            # Check 1: Verify the block's own hash (based on its content)
            if current_block.hash != current_block.compute_hash():
                print(f"Chain Invalid: Block {i} stored hash mismatch.")
                return False

            # Check 2: Verify the previous hash link (Skip Genesis)
            if previous_block:
                if current_block.previous_hash != previous_block.hash:
                    print(f"Chain Invalid: Block {i} previous hash link broken.")
                    return False

            # Check 3: Verify the Host Authority's signature (PoA)
            # The signature proves the host approved the *content* hash.
            if not verify_signature(
                self.host_public_key, 
                current_block.compute_hash(), # Hash of the content
                current_block.host_signature
            ):
                print(f"Chain Invalid: Block {i} Host signature verification failed.")
                return False
                
            previous_block = current_block

        return True
