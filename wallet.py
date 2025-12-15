import hashlib
import json
import binascii
from ecdsa import SigningKey, SECP256k1, VerifyingKey, BadSignatureError

# --- Hashing Utility ---

def hash_data(data):
    """Creates a SHA-256 hash of the input data (string or dict)."""
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

# --- Key Management ---

def generate_key_pair():
    """Generates a new ECC (SECP256k1) private and public key pair."""
    # Private Key
    private_key_sk = SigningKey.generate(curve=SECP256k1)
    private_key = private_key_sk.to_string().hex() 

    # Public Key (Uncompressed)
    public_key_vk = private_key_sk.get_verifying_key()
    public_key = '04' + public_key_vk.to_string().hex() 
    
    return private_key, public_key

# --- Digital Signature ---

def sign_transaction(private_key_hex, data_to_sign_hash):
    """Signs the hash of the data using the private key."""
    try:
        sk = SigningKey.from_string(binascii.unhexlify(private_key_hex), curve=SECP256k1)
        signature_bytes = sk.sign(data_to_sign_hash.encode('utf-8'), hashfunc=hashlib.sha256)
        return binascii.hexlify(signature_bytes).decode('utf-8')
    except Exception as e:
        print(f"Error signing transaction: {e}")
        return None

def verify_signature(public_key_hex, data_to_verify_hash, signature_hex):
    """Verifies a digital signature using the public key."""
    try:
        # Extract raw key (remove '04' prefix)
        vk_string = binascii.unhexlify(public_key_hex[2:])
        vk = VerifyingKey.from_string(vk_string, curve=SECP256k1)
        signature_bytes = binascii.unhexlify(signature_hex)
        
        return vk.verify(signature_bytes, data_to_verify_hash.encode('utf-8'), hashfunc=hashlib.sha256)
    except BadSignatureError:
        return False
    except Exception as e:
        print(f"Signature error: {e}")
        return False
