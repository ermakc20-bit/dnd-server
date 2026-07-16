import hashlib
import secrets
from itsdangerous import URLSafeTimedSerializer
from app.core.config import SECRET_KEY

serializer = URLSafeTimedSerializer(SECRET_KEY)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def decode_session(token: str):
    try:
        return serializer.loads(token, max_age=60 * 60 * 24 * 7)
    except:
        return None

def generate_table_link() -> str:
    return secrets.token_urlsafe(8)
