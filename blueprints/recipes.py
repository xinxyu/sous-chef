"""Recipes blueprint: CRUD for saved recipes (per user)."""
import uuid
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from sqlalchemy import select

from extensions import db
from models import User, SavedRecipe
from utils.auth import get_current_user_id, require_auth

logger = logging.getLogger(__name__)
bp = Blueprint("recipes", __name__, url_prefix="/recipes")


def _recipe_row_to_dict(row: SavedRecipe, user_id: str) -> dict:
    """Build API recipe dict from SavedRecipe row."""
    out = dict(row.data)
    out["id"] = str(row.recipe_id)
    out["user_id"] = user_id
    out["saved_at"] = row.saved_at.isoformat() if hasattr(row.saved_at, "isoformat") else row.saved_at
    if row.title is not None:
        out["title"] = row.title
    return out


@bp.route("", methods=["POST"])
@require_auth
def save_recipe():
    try:
        user_id = get_current_user_id()
        data = request.get_json()
        if not data:
            return jsonify({"error": "Recipe data is required"}), 400
        recipe_id = data.get("id") or str(uuid.uuid4())
        try:
            recipe_uuid = uuid.UUID(recipe_id) if isinstance(recipe_id, str) else recipe_id
        except (ValueError, TypeError):
            recipe_uuid = uuid.uuid4()
            recipe_id = str(recipe_uuid)

        recipe_data = {
            "id": recipe_id,
            "user_id": user_id,
            "title": data.get("title"),
            "total_time": data.get("total_time"),
            "yields": data.get("yields"),
            "ingredients": data.get("ingredients", []),
            "instructions": data.get("instructions", []),
            "image": data.get("image"),
            "host": data.get("host"),
            "nutrients": data.get("nutrients"),
            "source_url": data.get("source_url"),
            "saved_at": datetime.now().isoformat(),
        }
        saved_at = datetime.now()
        title = recipe_data.get("title")
        user_uuid = uuid.UUID(user_id)

        existing = db.session.execute(
            select(SavedRecipe).where(
                SavedRecipe.user_id == user_uuid,
                SavedRecipe.recipe_id == recipe_uuid,
            )
        ).scalar_one_or_none()
        if existing:
            existing.saved_at = saved_at
            existing.title = title
            existing.data = recipe_data
        else:
            row = SavedRecipe(
                user_id=user_uuid,
                recipe_id=recipe_uuid,
                saved_at=saved_at,
                title=title,
                data=recipe_data,
            )
            db.session.add(row)
        db.session.commit()
        logger.info("Saved recipe %s for user %s", recipe_id, user_id)
        return jsonify(recipe_data), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error saving recipe: %s", e)
        return jsonify({"error": f"Failed to save recipe: {str(e)}"}), 500


@bp.route("", methods=["GET"])
@require_auth
def list_recipes():
    try:
        user_id = get_current_user_id()
        user_uuid = uuid.UUID(user_id)
        rows = db.session.execute(
            select(SavedRecipe).where(SavedRecipe.user_id == user_uuid).order_by(SavedRecipe.saved_at.desc())
        ).scalars().all()
        out = [_recipe_row_to_dict(r, user_id) for r in rows]
        return jsonify(out), 200
    except Exception as e:
        logger.error("Error listing recipes: %s", e)
        return jsonify({"error": f"Failed to list recipes: {str(e)}"}), 500


@bp.route("/<recipe_id>", methods=["GET"])
@require_auth
def get_recipe(recipe_id):
    try:
        user_id = get_current_user_id()
        try:
            recipe_uuid = uuid.UUID(recipe_id)
        except (ValueError, TypeError):
            return jsonify({"error": "Recipe not found"}), 404
        user_uuid = uuid.UUID(user_id)
        row = db.session.execute(
            select(SavedRecipe).where(
                SavedRecipe.user_id == user_uuid,
                SavedRecipe.recipe_id == recipe_uuid,
            )
        ).scalar_one_or_none()
        if not row:
            return jsonify({"error": "Recipe not found"}), 404
        return jsonify(_recipe_row_to_dict(row, user_id)), 200
    except Exception as e:
        logger.error("Error getting recipe: %s", e)
        return jsonify({"error": f"Failed to get recipe: {str(e)}"}), 500


@bp.route("/<recipe_id>", methods=["DELETE"])
@require_auth
def delete_recipe(recipe_id):
    try:
        user_id = get_current_user_id()
        try:
            recipe_uuid = uuid.UUID(recipe_id)
        except (ValueError, TypeError):
            return jsonify({"error": "Recipe not found"}), 404
        user_uuid = uuid.UUID(user_id)
        row = db.session.execute(
            select(SavedRecipe).where(
                SavedRecipe.user_id == user_uuid,
                SavedRecipe.recipe_id == recipe_uuid,
            )
        ).scalar_one_or_none()
        if not row:
            return jsonify({"error": "Recipe not found"}), 404
        db.session.delete(row)
        db.session.commit()
        logger.info("Deleted recipe %s for user %s", recipe_id, user_id)
        return jsonify({"message": "Recipe deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error("Error deleting recipe: %s", e)
        return jsonify({"error": f"Failed to delete recipe: {str(e)}"}), 500
