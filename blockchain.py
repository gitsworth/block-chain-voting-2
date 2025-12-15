import json
import time
import os
from wallet import hash_data, sign_transaction, verify_signature

BLOCKCHAIN_FILE = 'blockchain.json'

# --- Host Keys (Set dynamically from App) ---
HOST_PUBLIC_KEY = None
HOST_PRIVATE_KEY = None

def set_host_keys(public, private):
    global HOST_PUBLIC_KEY, HOST_PRIVATE_KEY
    HOST_PUBLIC_KEY = public
    HOST_PRIVATE_KEY = private

# --- Persistence ---
def load_chain():
    if os.path.exists(BLOCKCHAIN_FILE):
        try:
            with open(BLOCKCHAIN_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_chain(chain):
    with open(BLOCKCHAIN_FILE, 'w') as f:
        json.dump(chain, f, indent=4)

# --- Logic ---
def calculate_block_hash(block):
    """Calculates the SHA-256 hash for a block's content."""
    block_copy = block.copy()
    block_copy.pop('hash', None)
    block_copy.pop('signature', None)
    return hash_data(block_copy)

def create_genesis_block():
    """Creates and signs the first block in the chain."""
    if not HOST_PRIVATE_KEY:
        raise ValueError("Host Private Key must be set to create genesis block.")
        
    genesis_block = {
        'index': 1,
        'timestamp': time.time(),
        'transactions': [{'note': 'Genesis Block'}],
        'proof': 0,
        'previous_hash': '0'
    }
    genesis_hash = calculate_block_hash(genesis_block)
    
    # Proof-of-Authority: Host signs the block content
    genesis_block['hash'] = genesis_hash
    genesis_block['signature'] = sign_transaction(HOST_PRIVATE_KEY, genesis_hash)
    
    chain = [genesis_block]
    save_chain(chain)
    return chain

def initialize_blockchain():
    """Loads the chain or creates the genesis block if it doesn't exist."""
    chain = load_chain()
    # Only create genesis if the chain is empty AND Host keys are available
    if not chain and HOST_PRIVATE_KEY:
        return create_genesis_block()
    return chain

def new_block(chain, pending_transactions):
    """Mines a new block by incorporating new transactions and signing it."""
    if not HOST_PRIVATE_KEY:
        raise ValueError("Host Private Key must be set to mine new blocks.")

    last_block = chain[-1]
    block = {
        'index': last_block['index'] + 1,
        'timestamp': time.time(),
        'transactions': pending_transactions,
        'proof': 100, # PoA doesn't use complex proof-of-work
        'previous_hash': last_block['hash']
    }
    block_hash = calculate_block_hash(block)
    
    # Proof-of-Authority: Host signs the new block
    block['hash'] = block_hash
    block['signature'] = sign_transaction(HOST_PRIVATE_KEY, block_hash)
    
    chain.append(block)
    save_chain(chain)
    return block

def is_chain_valid(chain):
    """Verifies the integrity of the entire chain."""
    if not chain: return True, 0, "Empty"
    
    for i in range(1, len(chain)):
        current = chain[i]
        prev = chain[i-1]
        
        # 1. Check Linkage
        if current['previous_hash'] != prev['hash']:
            return False, i, "Broken Link (Previous hash mismatch)"
            
        # 2. Check Host Signature (Proof-of-Authority)
        content_hash = calculate_block_hash(current)
        if not verify_signature(HOST_PUBLIC_KEY, content_hash, current['signature']):
            return False, i, "Invalid Host Signature (Block content was tampered with)"
            
    return True, None, None
