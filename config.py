"""App config from environment."""
import os
from dotenv import load_dotenv

load_dotenv()


def database_uri():
    """SQLAlchemy URI for PostgreSQL. Use psycopg (v3) driver if plain postgresql://."""
    url = os.environ.get("DATABASE_URL", "")
    if url and url.startswith("postgresql://") and "postgresql+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def cors_origins():
    raw = os.environ.get("CORS_ORIGINS", os.environ.get("FRONTEND_ORIGIN", ""))
    return [o.strip() for o in raw.split(",") if o.strip()]


def session_cookie_secure():
    v = (os.environ.get("SESSION_COOKIE_SECURE") or "").strip().lower()
    return v in ("1", "true", "yes")
