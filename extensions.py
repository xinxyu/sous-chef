"""Flask extensions (e.g. SQLAlchemy) initialized here to avoid circular imports."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
