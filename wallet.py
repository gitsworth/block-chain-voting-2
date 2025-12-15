import hashlib
import binascii
from ecdsa import SigningKey, SECP256k1, VerifyingKey, BadSignatureError

def generate_key_pair():
    """Generates a private and public key pair using ECDSA (secp256k1)."""
    # Generate the private key
    private_key_obj = SigningKey.generate(curve=SECP256k1)
    private_key_hex = private_key_obj.to_string().hex()

    # Generate the public key (uncompressed format, starts with '04')
    public_key_obj = private_key_obj.get_verifying_key()
    public_key_hex = '04' + public_key_obj.to_string().hex()
    
    return private_key_hex, public_key_hex

def sign_transaction(private_key_hex, data):
    """Signs a piece of data (e.g., a vote transaction) with the private key."""
    try:
        # Reconstruct the SigningKey object from the hexadecimal string
        private_key_bytes = binascii.unhexlify(private_key_hex)
        sk = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        
        # Hash the data before signing
        hashed_data = hashlib.sha256(data.encode()).digest()
        
        # Sign the hashed data
        signature = sk.sign(hashed_data)
        
        return signature.hex()
    except Exception as e:
        print(f"Error signing transaction: {e}")
        return None

def verify_signature(public_key_hex, data, signature_hex):
    """Verifies a signature against the public key and the original data."""
    try:
        # Reconstruct the VerifyingKey object from the hexadecimal string (omitting '04')
        public_key_bytes = binascii.unhexlify(public_key_hex[2:])
        vk = VerifyingKey.from_string(public_key_bytes, curve=SECP256k1)
        
        # Convert signature to bytes
        signature_bytes = binascii.unhexlify(signature_hex)
        
        # Hash the data the same way it was hashed during signing
        hashed_data = hashlib.sha256(data.encode()).digest()
        
        # Verify the signature
        return vk.verify(signature_bytes, hashed_data)
        
    except BadSignatureError:
        return False
    except Exception as e:
        print(f"Error verifying signature: {e}")
        return False
