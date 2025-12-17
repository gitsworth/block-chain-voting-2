import json
import time
import hashlib
import streamlit as st
from firestore_service import get_ledger, save_ledger

class Blockchain:
    def __init__(self):
        self.chain, self.pending_transactions = get_ledger()
        if not self.chain:
            # Create the genesis block if ledger is empty
            self.new_block(proof=100, previous_hash='1')
            save_ledger(self.chain, self.pending_transactions)

    def hash(self, block_data):
        """Creates a SHA-256 hash of a block's data."""
        # Convert the dictionary to a JSON string and encode it for hashing
        block_string = json.dumps(block_data, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def new_block(self, proof, previous_hash=None):
        """
        Creates a new Block and adds it to the chain.
        """
        block = {
            'index': len(self.chain),
            'timestamp': time.time(),
            'transactions': self.pending_transactions,
            'proof': proof,
            'previousHash': previous_hash or self.hash(self.chain[-1]),
        }

        # Reset the current list of pending transactions
        self.pending_transactions = []

        # Calculate the block's hash immediately
        block['hash'] = self.hash(block)
        
        self.chain.append(block)
        save_ledger(self.chain, self.pending_transactions)
        return block

    def new_transaction(self, sender_id, recipient_id, amount):
        """
        Adds a new transaction (vote) to the list of pending transactions.
        Recipient_id here is the Firestore document ID of the vote.
        """
        transaction = {
            'sender': sender_id, # Voter ID
            'recipient': recipient_id, # Vote Doc ID
            'amount': amount,
            'timestamp': time.time()
        }
        self.pending_transactions.append(transaction)
        save_ledger(self.chain, self.pending_transactions)

    @property
    def last_block(self):
        """Returns the last block in the chain."""
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        """
        Simple Proof of Work Algorithm:
         - Find a number p' such that hash(pp') contains 4 leading zeros
         - Where p is the previous proof, and p' is the new proof
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    def valid_proof(self, last_proof, proof):
        """
        Validates the Proof: Does hash(last_proof, proof) contain 4 leading zeros?
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def is_chain_valid(self, chain):
        """Determines if a given blockchain is valid."""
        # Simplified validation: checks hashes and proof of work for all blocks
        for i in range(1, len(chain)):
            block = chain[i]
            last_block = chain[i-1]

            # Check that the hash of the block is correct
            if block['previousHash'] != self.hash(last_block):
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

        return True

# Initialize the blockchain in Streamlit's session state
def get_blockchain():
    """Initializes and retrieves the Blockchain instance from session state."""
    if 'blockchain' not in st.session_state:
        st.session_state.blockchain = Blockchain()
    return st.session_state.blockchain
