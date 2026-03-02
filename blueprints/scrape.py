"""Scrape blueprint: POST /scrape to extract recipe from URL."""
import logging
import os
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


def _proxy_kwargs():
    """Return proxies dict for requests if SCRAPING_PROXY is set (e.g. Bright Data)."""
    proxy = os.environ.get("SCRAPING_PROXY")
    if not proxy:
        return {}
    return {"proxies": {"http": proxy, "https": proxy}}


def _fetch_with_proxy(url: str, headers: dict) -> str | None:
    """Fetch via SCRAPING_PROXY (Bright Data, ScraperAPI, etc.)."""
    proxy = os.environ.get("SCRAPING_PROXY")
    if not proxy:
        return None
    try:
        resp = requests.get(
            url,
            headers=headers,
            proxies={"http": proxy, "https": proxy},
            timeout=30,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        logger.warning("Proxy fetch failed: %s", e)
        return None


def _fetch_with_curl_cffi(url: str, headers: dict) -> str | None:
    """Fetch with curl_cffi (Chrome TLS fingerprint). Optional proxy via SCRAPING_PROXY."""
    try:
        from curl_cffi import requests as curl_requests
        proxy = os.environ.get("SCRAPING_PROXY")
        resp = curl_requests.get(
            url,
            headers=headers,
            timeout=20,
            impersonate="chrome120",
            proxy=proxy or None,
        )
        resp.raise_for_status()
        return resp.text
    except ImportError:
        return None
    except Exception:
        return None


def _user_friendly_fetch_error(status_code: int, url: str) -> str:
    """User-facing message for 402/403 from recipe sites."""
    if status_code == 402:
        return (
            "This recipe site is blocking requests from this server (402 Payment Required). "
            "Set SCRAPING_PROXY to a proxy URL (e.g. Bright Data) for deployed servers."
        )
    if status_code == 403:
        return (
            "This recipe site blocked the request (403 Forbidden). "
            "Set SCRAPING_PROXY to a proxy URL (e.g. Bright Data) for deployed servers."
        )
    return f"Failed to fetch URL: {status_code} Client Error for url: {url}"


def _fetch_html(url: str) -> str:
    """Fetch HTML. If SCRAPING_PROXY is set, use proxy first; then curl_cffi, cloudscraper, requests."""
    headers = dict(_DEFAULT_HEADERS)
    parsed = urlparse(url)
    if parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    # 0. Proxy (Bright Data, ScraperAPI, etc.) when set – avoids datacenter IP blocks
    if os.environ.get("SCRAPING_PROXY"):
        html = _fetch_with_proxy(url, headers)
        if html:
            return html

    # 1. curl_cffi (Chrome TLS fingerprint)
    html = _fetch_with_curl_cffi(url, headers)
    if html:
        return html

    # 2. cloudscraper
    scraper = _get_cloudscraper()
    if scraper:
        try:
            kwargs = _proxy_kwargs()
            resp = scraper.get(url, timeout=20, **kwargs)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code in (402, 403):
                raise
            pass

    # 3. plain requests (with optional proxy)
    resp = requests.get(url, headers=headers, timeout=15, **_proxy_kwargs())
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
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else 500
        msg = _user_friendly_fetch_error(status, url) if status in (402, 403) else str(e)
        logger.error("Failed to fetch URL: %s", e)
        return jsonify({"error": msg}), 500
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
