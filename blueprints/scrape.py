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


def _fetch_with_curl_cffi(url: str, headers: dict) -> str | None:
    """Fetch with curl_cffi (Chrome TLS fingerprint). Returns HTML or None on failure."""
    try:
        from curl_cffi import requests as curl_requests
        resp = curl_requests.get(url, headers=headers, timeout=20, impersonate="chrome120")
        resp.raise_for_status()
        return resp.text
    except ImportError:
        return None
    except Exception:
        return None


def _fetch_html(url: str) -> str:
    """Fetch HTML. Prefers curl_cffi (best Cloudflare bypass), then cloudscraper, then requests."""
    headers = dict(_DEFAULT_HEADERS)
    parsed = urlparse(url)
    if parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    # 1. curl_cffi (Chrome TLS fingerprint - most reliable for Cloudflare)
    html = _fetch_with_curl_cffi(url, headers)
    if html:
        return html

    # 2. cloudscraper (Cloudflare JS challenge solver)
    scraper = _get_cloudscraper()
    if scraper:
        try:
            resp = scraper.get(url, timeout=20)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.exceptions.HTTPError:
            pass

    # 3. plain requests
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
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
