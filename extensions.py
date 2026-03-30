"""Flask extensions (e.g. SQLAlchemy) initialized here to avoid circular imports."""
from authlib.integrations.flask_client import OAuth
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
oauth = OAuth()
