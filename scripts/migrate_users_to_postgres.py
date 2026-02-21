#!/usr/bin/env python3
"""
One-time migration: import users.json into PostgreSQL users table.
Requires DATABASE_URL to be set. Run from the sous-chef project root:

  python scripts/migrate_users_to_postgres.py

Or with explicit path to JSON:

  python scripts/migrate_users_to_postgres.py path/to/users.json
"""
import json
import os
import sys
from datetime import datetime

# Ensure project root is on path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: Set DATABASE_URL before running this script.", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1] if len(sys.argv) > 1 else "users.json"
    if not os.path.isfile(json_path):
        print(f"ERROR: File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    from app import init_db, db_create_user

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    init_db()
    count = 0
    for username, user in data.items():
        user_id = user["id"]
        email = user.get("email")
        password_hash = user["password_hash"]
        created_at_str = user.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else datetime.now()
        except (ValueError, TypeError):
            created_at = datetime.now()
        try:
            db_create_user(user_id, username, email, password_hash, created_at, email_verified=True)
            count += 1
        except Exception as e:
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"Skip (already exists): {username}")
            else:
                raise
    print(f"Migrated {count} users from {json_path} to PostgreSQL.")


if __name__ == "__main__":
    main()
