# wallet.py - Handles cryptographic operations: key generation, signing, and verification.
# Uses the 'ecdsa' library for Elliptic Curve Digital Signature Algorithm.
import hashlib
import time
from datetime import datetime
from ecdsa import SigningKey, VerifyingKey, SECP256k1
import base64

# --- 1. Key Management ---

def generate_key_pair():
    """
    Generates a new ECDSA Public/Private key pair using the SECP256k1 curve (like Bitcoin).
    
    Returns:
        tuple: (private_key_hex, public_key_hex)
    """
    # Generate the signing key (Private Key)
    sk = SigningKey.generate(curve=SECP256k1)
    # Get the verifying key (Public Key)
    vk = sk.get_verifying_key()
    
    # Convert to hex strings for storage and use
    private_key_hex = sk.to_string().hex()
    # The public key includes the '04' prefix for uncompressed format
    public_key_hex = '04' + vk.to_string().hex() 
    
    return private_key_hex, public_key_hex

def get_signing_key(private_key_hex):
    """Converts a private key hex string back into a SigningKey object."""
    try:
        # Decode hex to bytes, then create the SigningKey
        private_key_bytes = bytes.fromhex(private_key_hex)
        return SigningKey.from_string(private_key_bytes, curve=SECP256k1)
    except Exception as e:
        # This occurs if the private key format is incorrect
        print(f"Error loading signing key: {e}")
        return None

def get_verifying_key(public_key_hex):
    """Converts a public key hex string back into a VerifyingKey object."""
    try:
        # Public key must be decoded, stripping the '04' prefix if present
        if public_key_hex.startswith('04'):
            public_key_bytes = bytes.fromhex(public_key_hex[2:])
        else:
            public_key_bytes = bytes.fromhex(public_key_hex)
            
        return VerifyingKey.from_string(public_key_bytes, curve=SECP256k1)
    except Exception as e:
        # This occurs if the public key format is incorrect
        print(f"Error loading verifying key: {e}")
        return None

# --- 2. Hashing and Signature ---

def hash_data(data):
    """
    Computes the SHA256 hash of the input data (string).
    
    Args:
        data (str): The data to be hashed (e.g., transaction string, block content).
        
    Returns:
        str: The SHA256 hash in hexadecimal format.
    """
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

def sign_data(private_key_hex, data):
    """
    Digitally signs a piece of data using the corresponding private key.
    
    Args:
        private_key_hex (str): The private key of the signer (voter or host).
        data (str): The data to be signed (e.g., the hash of a vote transaction).
        
    Returns:
        str: The digital signature encoded in Base64 (for compactness).
    """
    sk = get_signing_key(private_key_hex)
    if sk is None:
        return ""
    
    # Sign the SHA256 hash of the data
    signature_bytes = sk.sign(data.encode('utf-8'), hashfunc=hashlib.sha256)
    
    # Encode the signature bytes to Base64 string for easy storage/transfer
    return base64.b64encode(signature_bytes).decode('utf-8')

def verify_signature(public_key_hex, data, signature_b64):
    """
    Verifies a digital signature using the public key and the original data.
    
    Args:
        public_key_hex (str): The public key of the original signer.
        data (str): The original data that was signed.
        signature_b64 (str): The Base64 encoded signature to verify.
        
    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    vk = get_verifying_key(public_key_hex)
    if vk is None:
        return False

    try:
        # Decode the Base64 signature back to bytes
        signature_bytes = base64.b64decode(signature_b64)
        
        # Verify the signature against the SHA256 hash of the data
        return vk.verify(signature_bytes, data.encode('utf-8'), hashfunc=hashlib.sha256)
    except Exception as e:
        # This catches exceptions if the signature is malformed or invalid
        print(f"Signature verification failed unexpectedly: {e}")
        return False
        
# --- 3. PII and Utility Functions ---

def get_pii_id(name, dob, email):
    """
    Generates a unique, deterministic PII ID by hashing sensitive voter data.
    This ID is used as the Firestore document ID for voter records (for Host management).
    """
    pii_string = f"{name.lower().strip()}|{dob.strip()}|{email.lower().strip()}"
    return hash_data(pii_string)

def calculate_age(dob_str):
    """
    Calculates age based on a YYYY-MM-DD date of birth string.
    """
    try:
        birth_date = datetime.strptime(dob_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        # Calculate age
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age
    except:
        return -1 # Return -1 if DOB is malformed
