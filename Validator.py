import streamlit as st
import time
from firestore_service import get_unmined_votes, update_candidate_vote_count, mark_vote_mined
from blockchain_core import get_blockchain

def render_validator_portal():
    """Renders the Validator portal."""
    validator_id = st.session_state.context_id
    bc = get_blockchain()

    st.title(f"Validator Portal ({validator_id})")
    st.info("Your role is to validate votes by mining blocks and auditing the chain.")
    
    st.markdown("---")
    
    # Mining Section
    st.subheader("⛏️ Mine Block & Validate Chain")
    pending_count = len(bc.pending_transactions)
    st.metric("Pending Transactions (Votes)", pending_count)

    if st.button("Mine New Block", disabled=(pending_count == 0), use_container_width=True):
        
        with st.spinner(f'Starting Proof-of-Work with {pending_count} transactions...'):
            last_block = bc.last_block
            last_proof = last_block['proof']
            
            # --- Proof of Work ---
            start_time = time.time()
            new_proof = bc.proof_of_work(last_proof)
            mining_duration = time.time() - start_time
            
            # --- Create Block ---
            new_block = bc.new_block(new_proof)
            
            # --- Process Transactions (Update Firestore) ---
            for tx in new_block['transactions']:
                vote_doc_id = tx['recipient']
                # The vote must be retrieved from the original database to get the candidate_id
                # In this simplified model, we assume the candidate ID is in the tx (which is not, 
                # so we rely on fetching unmined votes to link the doc ID to the candidate ID).
                
                # We use the unmined votes list to find the details, but a proper solution
                # would fetch the specific vote document by ID (tx['recipient'])
                
                # Fetch the unmined votes to find the corresponding candidate ID
                unmined = get_unmined_votes()
                vote_data = next((v for v in unmined if v['id'] == vote_doc_id), None)

                if vote_data:
                    candidate_id = vote_data['candidateId']
                    update_candidate_vote_count(candidate_id, tx['amount'])
                    mark_vote_mined(vote_doc_id)
                else:
                    st.warning(f"Vote document {vote_doc_id} not found or already mined in a previous run.")

            st.success(f"Block #{new_block['index']} mined in {mining_duration:.2f}s! Transactions processed: {len(new_block['transactions'])}")
            st.experimental_rerun()
    
    st.markdown("---")
    st.subheader("⛓️ Blockchain Audit Log")
    
    # Display the chain
    chain = bc.chain
    st.markdown(f"**Current Chain Length: {len(chain)}**")
    
    # Display blocks in reverse order
    for block in reversed(chain):
        with st.expander(f"Block #{block['index']} (Hash: {block['hash'][:10]}...)", expanded=block['index'] == len(chain) - 1):
            st.code(f"Timestamp: {time.ctime(block['timestamp'])}")
            st.code(f"Proof: {block['proof']}")
            st.code(f"Previous Hash: {block['previousHash'][:10]}...")
            
            st.markdown(f"**Transactions ({len(block['transactions'])})**:")
            if block['transactions']:
                for tx in block['transactions']:
                    st.code(f"  Voter: {tx['sender']} -> Vote Doc ID: {tx['recipient'][:8]}... (Amount: {tx['amount']})")
            else:
                st.write("  *No transactions in this block.*")
