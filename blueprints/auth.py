"""Auth blueprint: register, login, logout, verify-email, forgot/reset password, Google OAuth, me."""
import logging
import os
import re
import secrets
import urllib.parse
import uuid
from datetime import datetime, timedelta

import requests
from flask import Blueprint, redirect, request, jsonify, session, url_for
from sqlalchemy import select, and_

from extensions import db, oauth
from models import User, EmailVerificationToken, PasswordResetToken
from utils.auth import hash_password, encode_jwt, get_current_user_id
from utils.email import send_email

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__, url_prefix="/auth")


def _timedelta_hours(hours):
    return timedelta(hours=hours)


def _base_url():
    raw = (os.environ.get("APP_BASE_URL") or os.environ.get("FRONTEND_ORIGIN") or "http://localhost:4200").strip()
    if not raw:
        raw = "http://localhost:4200"
    raw = raw.rstrip("/")
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw


def _google_oauth_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def _google_redirect_uri():
    return (os.environ.get("GOOGLE_REDIRECT_URI") or "").strip() or None


def _sanitize_username_base(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (s or "").strip()).strip("_")
    return (s[:40] if s else "user") or "user"


def _ensure_unique_username(base: str) -> str:
    base = _sanitize_username_base(base)
    if len(base) < 3:
        base = f"{base}_sc"
    candidate = base
    n = 0
    while True:
        existing = db.session.execute(select(User).where(User.username == candidate)).scalar_one_or_none()
        if not existing:
            return candidate
        n += 1
        candidate = f"{base}_{n}"


def _fetch_google_userinfo(access_token: str) -> dict | None:
    try:
        r = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Google userinfo request failed: %s", e)
        return None


@bp.route("/google", methods=["GET"])
def google_login():
    if not _google_oauth_configured():
        return jsonify({"error": "Google sign-in is not configured"}), 503
    redirect_uri = _google_redirect_uri() or url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/google/callback", methods=["GET"])
def google_callback():
    frontend = _base_url()
    if not _google_oauth_configured():
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('Google sign-in is not configured')}")

    try:
        token = oauth.google.authorize_access_token()
    except Exception as e:
        logger.warning("Google OAuth callback failed: %s", e)
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('Google sign-in was cancelled or failed')}")

    access_token = (token or {}).get("access_token")
    if not access_token:
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('No access token from Google')}")

    userinfo = _fetch_google_userinfo(access_token)
    if not userinfo:
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('Could not load Google profile')}")

    google_sub = (userinfo.get("sub") or "").strip()
    email = (userinfo.get("email") or "").strip()
    if not google_sub:
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('Invalid Google account')}")
    if not email:
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('Google did not provide an email')}")

    email_lower = email.lower()
    user = db.session.execute(select(User).where(User.google_sub == google_sub)).scalar_one_or_none()
    if not user:
        user = db.session.execute(
            select(User).where(
                and_(
                    User.email.isnot(None),
                    db.func.lower(db.func.trim(User.email)) == email_lower,
                )
            )
        ).scalar_one_or_none()
        if user:
            if user.google_sub and user.google_sub != google_sub:
                return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('This email is linked to another Google account')}")
            user.google_sub = google_sub

    if not user:
        local = email.split("@")[0] if "@" in email else "user"
        username = _ensure_unique_username(local)
        user_id = uuid.uuid4()
        created_at = datetime.now()
        user = User(
            id=user_id,
            username=username,
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            created_at=created_at,
            email_verified=True,
            google_sub=google_sub,
        )
        db.session.add(user)
    else:
        if not user.email_verified:
            user.email_verified = True

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error("Google OAuth user persist failed: %s", e)
        return redirect(f"{frontend}/#oauth_error={urllib.parse.quote('Could not save account')}")

    session["user_id"] = str(user.id)
    session["username"] = user.username
    jwt_token = encode_jwt(str(user.id))
    frag = urllib.parse.quote(jwt_token, safe="")
    logger.info("Google OAuth login: user_id=%s", user.id)
    return redirect(f"{frontend}/#oauth_token={frag}")


@bp.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        email = (data.get("email") or "").strip()
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if not email:
            return jsonify({"error": "Email is required for registration"}), 400
        if len(username) < 3:
            return jsonify({"error": "Username must be at least 3 characters"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        if db.session.execute(select(User).where(User.username == username)).scalar_one_or_none():
            return jsonify({"error": "Username already exists"}), 400
        if db.session.execute(
            select(User).where(
                and_(
                    User.email.isnot(None),
                    db.func.lower(db.func.trim(User.email)) == email.strip().lower(),
                )
            )
        ).scalar_one_or_none():
            return jsonify({"error": "An account with this email already exists"}), 400

        user_id = uuid.uuid4()
        created_at = datetime.now()
        user = User(
            id=user_id,
            username=username,
            email=email or None,
            password_hash=hash_password(password),
            created_at=created_at,
            email_verified=False,
        )
        db.session.add(user)
        token_str = secrets.token_urlsafe(32)
        expires_at = datetime.now() + _timedelta_hours(24)
        evt = EmailVerificationToken(token=token_str, user_id=user_id, expires_at=expires_at)
        db.session.add(evt)
        db.session.commit()

        verify_url = f"{_base_url()}/verify-email?token={token_str}"
        body_text = f"Hi {username},\n\nPlease verify your email by opening this link:\n{verify_url}\n\nThe link expires in 24 hours."
        body_html = f'<p>Hi {username},</p><p>Please <a href="{verify_url}">verify your email</a>.</p><p>The link expires in 24 hours.</p>'
        send_email(email, "Verify your email - Sous Chef", body_text, body_html)
        logger.info("Registered new user: %s (pending verification)", username)
        return jsonify({
            "message": "Registration successful. Please check your email to verify your account before logging in.",
            "email_sent": True,
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error registering user: %s", e)
        return jsonify({"error": f"Failed to register user: {str(e)}"}), 500


@bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        user = db.session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user:
            return jsonify({"error": "Invalid username or password"}), 401
        if not user.email_verified:
            return jsonify({"error": "Please verify your email before logging in. Check your inbox for the verification link."}), 403
        if user.password_hash != hash_password(password):
            return jsonify({"error": "Invalid username or password"}), 401

        session["user_id"] = str(user.id)
        session["username"] = user.username
        token = encode_jwt(str(user.id))
        logger.info("User logged in: %s", username)
        return jsonify({
            "message": "Login successful",
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "google_account": bool(user.google_sub),
            },
            "token": token,
        }), 200
    except Exception as e:
        logger.error("Error logging in: %s", e)
        return jsonify({"error": f"Failed to login: {str(e)}"}), 500


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logout successful"}), 200


@bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    token = request.args.get("token") or (request.get_json() or {}).get("token")
    if not token:
        return jsonify({"error": "Verification token is required"}), 400
    evt = db.session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == token,
            EmailVerificationToken.expires_at > datetime.now(),
        )
    ).scalar_one_or_none()
    if not evt:
        return jsonify({"error": "Invalid or expired verification link. You may request a new one by registering again."}), 400
    user_id = evt.user_id
    user = db.session.get(User, user_id)
    if user:
        user.email_verified = True
    db.session.delete(evt)
    db.session.commit()
    logger.info("Email verified for user_id=%s", user_id)
    return jsonify({"message": "Email verified. You can now log in."}), 200


@bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    if not email:
        return jsonify({"error": "Email is required"}), 400
    user = db.session.execute(
        select(User).where(
            and_(
                User.email.isnot(None),
                db.func.lower(db.func.trim(User.email)) == email.strip().lower(),
            )
        )
    ).scalar_one_or_none()
    if not user:
        return jsonify({"message": "If an account exists with this email, you will receive a reset link."}), 200
    token_str = secrets.token_urlsafe(32)
    expires_at = datetime.now() + _timedelta_hours(1)
    prt = PasswordResetToken(token=token_str, user_id=user.id, expires_at=expires_at)
    db.session.add(prt)
    db.session.commit()
    reset_url = f"{_base_url()}/reset-password?token={token_str}"
    body_text = f"Hi {user.username},\n\nReset your password by opening this link:\n{reset_url}\n\nThe link expires in 1 hour."
    body_html = f'<p>Hi {user.username},</p><p><a href="{reset_url}">Reset your password</a>.</p><p>The link expires in 1 hour.</p>'
    send_email(email, "Reset your password - Sous Chef", body_text, body_html)
    return jsonify({"message": "If an account exists with this email, you will receive a reset link."}), 200


@bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    token = (data.get("token") or "").strip() or request.args.get("token")
    new_password = (data.get("new_password") or data.get("password") or "").strip()
    if not token:
        return jsonify({"error": "Reset token is required"}), 400
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    prt = db.session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.expires_at > datetime.now(),
        )
    ).scalar_one_or_none()
    if not prt:
        return jsonify({"error": "Invalid or expired reset link. Please request a new one."}), 400
    user_id = prt.user_id
    user = db.session.get(User, user_id)
    if user:
        user.password_hash = hash_password(new_password)
    db.session.delete(prt)
    db.session.commit()
    logger.info("Password reset for user_id=%s", user_id)
    return jsonify({"message": "Password updated. You can now log in with your new password."}), 200


@bp.route("/me", methods=["GET"])
def get_current_user():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"user": None}), 200
    try:
        user = db.session.get(User, uuid.UUID(user_id))
    except (ValueError, TypeError):
        return jsonify({"user": None}), 200
    if user:
        return jsonify({
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "google_account": bool(user.google_sub),
            }
        }), 200
    return jsonify({"user": None}), 200
