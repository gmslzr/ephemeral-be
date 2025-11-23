import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from hashlib import sha256
from app.config import settings


def _preprocess_password(password: str) -> bytes:
    """
    Preprocess password to handle bcrypt's 72-byte limit.
    Hash with SHA-256 first to get a fixed 32-byte value that's always < 72 bytes.
    Returns bytes for direct use with bcrypt.
    """
    # SHA-256 produces 32 bytes, which is well under the 72-byte limit
    return sha256(password.encode('utf-8')).digest()


def hash_password(plain: str) -> str:
    """Hash a plain text password using bcrypt"""
    # Preprocess to handle passwords longer than 72 bytes
    preprocessed = _preprocess_password(plain)
    # bcrypt.hashpw expects bytes and returns bytes
    hashed = bcrypt.hashpw(preprocessed, bcrypt.gensalt())
    # Return as string for storage
    return hashed.decode('utf-8')


def verify_password(plain: str, password_hash: str) -> bool:
    """Verify a plain text password against a hash"""
    # Preprocess to match the hashing process
    preprocessed = _preprocess_password(plain)
    # Convert password_hash string back to bytes
    password_hash_bytes = password_hash.encode('utf-8')
    # bcrypt.checkpw expects bytes for both arguments
    return bcrypt.checkpw(preprocessed, password_hash_bytes)


def create_jwt(user_id: str) -> str:
    """Create a JWT token for a user"""
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode = {"sub": str(user_id), "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")
    return encoded_jwt


def decode_jwt(token: str) -> Optional[str]:
    """Decode a JWT token and return user_id, or None if invalid"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        return user_id
    except JWTError:
        return None


def generate_lookup_hash(secret: str) -> str:
    """Generate SHA-256 hash for fast API key lookup"""
    return sha256(secret.encode('utf-8')).hexdigest()
