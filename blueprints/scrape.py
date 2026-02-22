"""Scrape blueprint: POST /scrape to extract recipe from URL."""
import logging
from flask import Blueprint, request, jsonify
from recipe_scrapers import scrape_me

from utils.scraping import fallback_parse_ingredients

logger = logging.getLogger(__name__)
bp = Blueprint("scrape", __name__)


@bp.route("/scrape", methods=["POST"])
def scrape_recipe():
    data = request.get_json()
    url = (data.get("url") if data else None) or request.form.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400
    logger.info("Scraping recipe from: %s", url)

    try:
        scraper = scrape_me(url, wild_mode=True)
        ingredients = scraper.ingredients()
        if ingredients is None or not isinstance(ingredients, list):
            ingredients = []
        logger.info("recipe-scrapers found %s ingredients", len(ingredients))

        if not ingredients:
            logger.warning("No ingredients from recipe-scrapers, trying fallback parser")
            ingredients = fallback_parse_ingredients(url)
            if ingredients:
                logger.info("Fallback parser extracted %s ingredients", len(ingredients))

        instructions = scraper.instructions_list()
        if instructions is None or not isinstance(instructions, list):
            instructions = []
        recipe_data = {
            "title": scraper.title() or "",
            "total_time": scraper.total_time(),
            "yields": scraper.yields() or "",
            "ingredients": ingredients,
            "instructions": instructions,
            "image": scraper.image() or "",
            "host": scraper.host() or "",
            "nutrients": scraper.nutrients() if hasattr(scraper, "nutrients") and scraper.nutrients() else None,
            "source_url": url,
        }
        return jsonify(recipe_data), 200
    except Exception as e:
        logger.warning("recipe-scrapers failed (%s), trying fallback parser only", e)
        try:
            ingredients = fallback_parse_ingredients(url)
            recipe_data = {
                "title": "",
                "total_time": None,
                "yields": "",
                "ingredients": ingredients or [],
                "instructions": [],
                "image": "",
                "host": "",
                "nutrients": None,
                "source_url": url,
            }
            return jsonify(recipe_data), 200
        except Exception as fallback_e:
            logger.error("Error scraping recipe: %s", fallback_e)
            return jsonify({"error": f"Failed to scrape recipe: {str(fallback_e)}"}), 500
