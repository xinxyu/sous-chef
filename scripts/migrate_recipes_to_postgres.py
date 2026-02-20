#!/usr/bin/env python3
"""
One-time migration: import saved_recipes.json into PostgreSQL (Option A schema).
Requires DATABASE_URL to be set. Run from the sous-chef project root:

  python scripts/migrate_recipes_to_postgres.py

Or with explicit path to JSON:

  python scripts/migrate_recipes_to_postgres.py path/to/saved_recipes.json
"""
import json
import os
import sys

# Ensure project root is on path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: Set DATABASE_URL before running this script.", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1] if len(sys.argv) > 1 else "saved_recipes.json"
    if not os.path.isfile(json_path):
        print(f"ERROR: File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    from app import init_db, db_save_recipe

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    init_db()
    count = 0
    for user_id, user_recipes in data.items():
        for recipe_id, recipe_data in user_recipes.items():
            db_save_recipe(user_id, recipe_id, recipe_data)
            count += 1
    print(f"Migrated {count} recipes from {json_path} to PostgreSQL.")

if __name__ == "__main__":
    main()
