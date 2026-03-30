"""Sous Chef Flask app: CORS, SQLAlchemy, blueprints (auth, recipes, scrape)."""
import argparse
import logging
import os

from flask import Flask
from flask_cors import CORS
from sqlalchemy import text

from config import database_uri, cors_origins, session_cookie_secure
from extensions import db, oauth
from blueprints import auth, recipes, scrape

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Database
uri = database_uri()
if uri:
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

oauth.init_app(app)
if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# CORS and session cookie
_origins = cors_origins()
_secure = session_cookie_secure()
if _secure:
    if _origins:
        if "http://localhost:4200" not in _origins:
            _origins.append("http://localhost:4200")
        if "http://127.0.0.1:4200" not in _origins:
            _origins.append("http://127.0.0.1:4200")
        CORS(app, supports_credentials=True, origins=_origins)
    else:
        CORS(app, supports_credentials=True)
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = True
else:
    CORS(app, supports_credentials=True)
    app.config["SESSION_COOKIE_SECURE"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Blueprints
app.register_blueprint(auth.bp)
app.register_blueprint(recipes.bp)
app.register_blueprint(scrape.bp)

# Create tables if they don't exist. For existing DBs, ensure email_verified column exists.
if uri:
    with app.app_context():
        db.create_all()
        # One-off: add email_verified to users if missing (legacy DBs)
        try:
            with db.engine.connect() as conn:
                conn.execute(text("""
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'email_verified'
                      ) THEN
                        ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT TRUE;
                      END IF;
                    END $$;
                """))
                conn.commit()
        except Exception as e:
            logger.warning("email_verified migration skip or failed: %s", e)
        try:
            with db.engine.connect() as conn:
                conn.execute(text("""
                    DO $$
                    BEGIN
                      IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'google_sub'
                      ) THEN
                        ALTER TABLE users ADD COLUMN google_sub VARCHAR(255) UNIQUE;
                      END IF;
                    END $$;
                """))
                conn.commit()
        except Exception as e:
            logger.warning("google_sub migration skip or failed: %s", e)
        logger.info("SQLAlchemy tables ready")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the sous-chef Flask API")
    parser.add_argument("-p", "--port", type=int, default=4100, help="Port to run on (default: 4100)")
    args = parser.parse_args()
    app.run(debug=True, host="0.0.0.0", port=args.port)
