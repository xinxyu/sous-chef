"""Scrape blueprint: POST /scrape to extract recipe from URL."""
import logging
from urllib.parse import urlparse

import requests
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

# Cloudflare bypass scraper - created once, reused for session cookies
_cloudscraper = None


def _get_cloudscraper():
    global _cloudscraper
    if _cloudscraper is None:
        try:
            import cloudscraper
            _cloudscraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "darwin", "desktop": True}
            )
        except ImportError:
            _cloudscraper = False
    return _cloudscraper if _cloudscraper else None


def _fetch_html(url: str) -> str:
    """Fetch HTML with browser-like headers. Uses cloudscraper on 403 for Cloudflare sites."""
    headers = dict(_DEFAULT_HEADERS)
    parsed = urlparse(url)
    if parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            scraper = _get_cloudscraper()
            if scraper:
                logger.info("Got 403, retrying with cloudscraper for Cloudflare bypass")
                resp = scraper.get(url, timeout=15)
                resp.raise_for_status()
            else:
                raise
        else:
            raise

    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


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
