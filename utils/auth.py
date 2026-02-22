"""Auth helpers: JWT, session, password hashing, require_auth decorator."""
import hashlib
import os
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, jsonify, session


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _jwt_secret():
    return os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")


def _jwt_algorithm():
    return "HS256"


def _jwt_expiry_days():
    return int(os.environ.get("JWT_EXPIRY_DAYS", "7"))


def encode_jwt(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=_jwt_expiry_days()),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
    except Exception:
        return None


def get_current_user_id() -> str | None:
    """Current user ID from Authorization Bearer token or session."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:].strip()
        payload = decode_jwt(token)
        if payload:
            return payload.get("user_id")
    return session.get("user_id")


def require_auth(f):
    """Decorator: return 401 if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user_id():
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated
