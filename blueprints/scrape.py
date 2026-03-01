"""Scrape blueprint: POST /scrape to extract recipe from URL."""
import logging
import urllib.request

from flask import Blueprint, request, jsonify
from recipe_scrapers import scrape_html

from utils.scraping import (
    fallback_parse_ingredients_from_html,
    fallback_parse_recipe_from_html,
    fallback_parse_recipe,
    _DEFAULT_HEADERS,
)

logger = logging.getLogger(__name__)
bp = Blueprint("scrape", __name__)


def _fetch_html(url: str) -> str:
    """Fetch HTML with browser-like headers to reduce 403 blocks."""
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode(errors="replace")


@bp.route("/scrape", methods=["POST"])
def scrape_recipe():
    data = request.get_json()
    url = (data.get("url") if data else None) or request.form.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400
    logger.info("Scraping recipe from: %s", url)

    try:
        html = _fetch_html(url)
    except Exception as e:
        logger.error("Failed to fetch URL: %s", e)
        return jsonify({"error": f"Failed to fetch URL: {str(e)}"}), 500

    try:
        scraper = scrape_html(html, org_url=url)
        title = scraper.title()
        if title is None:
            title = ""
        ingredients = scraper.ingredients()
        if ingredients is None or not isinstance(ingredients, list):
            ingredients = []

        if not ingredients:
            logger.warning("No ingredients from recipe-scrapers, trying fallback parser")
            ingredients = fallback_parse_ingredients_from_html(html)
            if ingredients:
                logger.info("Fallback parser extracted %s ingredients", len(ingredients))

        instructions = scraper.instructions_list()
        if instructions is None or not isinstance(instructions, list):
            instructions = []

        recipe_data = {
            "title": title or "",
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
        fallback = fallback_parse_recipe_from_html(html, url) or fallback_parse_recipe(url)
        if fallback:
            fallback["source_url"] = url
            return jsonify(fallback), 200
        logger.error("Error scraping recipe: %s", e)
        return jsonify({"error": f"Failed to scrape recipe: {str(e)}"}), 500
