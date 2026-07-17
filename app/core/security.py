import hashlib
import secrets
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request
from app.core.database import SessionLocal
from app.models import User

SECRET_KEY = "dnd_super_secret_key_2025_replace_me"
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

def get_current_user(request: Request):
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        data = decode_session(session_cookie)
        user_id = data.get("user_id")
        if user_id:
            db = SessionLocal()
            user = db.query(User).filter_by(id=user_id).first()
            db.close()
            return user
    except Exception:
        return None
    return None
