"""Scrape blueprint: POST /scrape to extract recipe from URL."""
import base64
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


# Bright Data proxy TLS. No cert in code: either install CA on server (use default verify)
# or set SCRAPING_CA_BUNDLE to a path or to PEM content in env. See docs.brightdata.com/general/account/ssl-certificate
SCRAPING_CA_BUNDLE_ENV = "SCRAPING_CA_BUNDLE"
_proxy_verify_logged = False
_ca_bundle_temp_path = None


def _proxy_verify():
    """Verify for proxy requests: SCRAPING_CA_BUNDLE (path or PEM string), or True (system trust)."""
    global _ca_bundle_temp_path, _proxy_verify_logged
    raw = os.environ.get(SCRAPING_CA_BUNDLE_ENV)
    if not raw:
        # No env: use default (True). Install Bright Data CA on the server and it will work.
        return True
    raw = raw.strip()
    # Path to existing file
    if os.path.isfile(raw):
        return raw
    # Base64-encoded PEM (single-line; works well on App Platform / Railway / Render)
    if raw and not raw.startswith("-----") and len(raw) > 100:
        try:
            raw = base64.b64decode(raw).decode()
        except Exception:
            pass
    # PEM content in env (e.g. pasted in deployment secrets) – no cert file in repo
    if "-----BEGIN" in raw and "-----END" in raw:
        if _ca_bundle_temp_path and os.path.isfile(_ca_bundle_temp_path):
            return _ca_bundle_temp_path
        try:
            import tempfile
            fd, path = tempfile.mkstemp(suffix=".crt", prefix="scraping_ca_")
            os.write(fd, raw.encode())
            os.close(fd)
            _ca_bundle_temp_path = path
            return path
        except Exception as e:
            logger.warning("Failed to write CA bundle from env: %s", e)
            if os.environ.get("SCRAPING_PROXY") and not _proxy_verify_logged:
                _proxy_verify_logged = True
                logger.info("Using verify=False for proxy. Install Bright Data CA on server or set SCRAPING_CA_BUNDLE.")
            return False
    # Looks like a path but file missing
    if not _proxy_verify_logged:
        _proxy_verify_logged = True
        logger.warning("SCRAPING_CA_BUNDLE file not found: %s. Using default system trust.", raw)
    return True


def _proxy_kwargs():
    """Return proxies and verify for requests when SCRAPING_PROXY is set."""
    proxy = os.environ.get("SCRAPING_PROXY")
    if not proxy:
        return {}
    kwargs = {"proxies": {"http": proxy, "https": proxy}}
    verify = _proxy_verify()
    if verify is not True:
        kwargs["verify"] = verify
    return kwargs


def _fetch_with_proxy(url: str, headers: dict) -> str | None:
    """Fetch via SCRAPING_PROXY (Bright Data, ScraperAPI, etc.). Uses SCRAPING_CA_BUNDLE if set."""
    proxy = os.environ.get("SCRAPING_PROXY")
    if not proxy:
        return None
    verify = _proxy_verify()
    try:
        resp = requests.get(
            url,
            headers=headers,
            proxies={"http": proxy, "https": proxy},
            timeout=30,
            verify=verify,
        )
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        logger.warning("Proxy fetch failed: %s", e)
        return None


def _fetch_with_curl_cffi(url: str, headers: dict, use_proxy: bool = True) -> str | None:
    """Fetch with curl_cffi. When use_proxy is True, uses SCRAPING_PROXY and SCRAPING_CA_BUNDLE for Bright Data TLS."""
    try:
        from curl_cffi import requests as curl_requests
        proxy = os.environ.get("SCRAPING_PROXY") if use_proxy else None
        verify = _proxy_verify() if use_proxy else True
        resp = curl_requests.get(
            url,
            headers=headers,
            timeout=20,
            impersonate="chrome120",
            proxy=proxy,
            verify=verify,
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
    """Fetch HTML. Try without proxy first; if that fails (blocked, errors), fall back to proxy when SCRAPING_PROXY is set."""
    headers = dict(_DEFAULT_HEADERS)
    parsed = urlparse(url)
    if parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    last_error = None

    # Phase 1: try without proxy
    html = _fetch_with_curl_cffi(url, headers, use_proxy=False)
    if html:
        return html

    scraper = _get_cloudscraper()
    if scraper:
        try:
            resp = scraper.get(url, timeout=20)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.exceptions.HTTPError as e:
            last_error = e
        except Exception as e:
            last_error = e

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.exceptions.HTTPError as e:
        last_error = e
    except Exception as e:
        last_error = e

    # Phase 2: fall back to proxy when configured
    if os.environ.get("SCRAPING_PROXY"):
        html = _fetch_with_proxy(url, headers)
        if html:
            return html

        html = _fetch_with_curl_cffi(url, headers, use_proxy=True)
        if html:
            return html

        if scraper:
            try:
                resp = scraper.get(url, timeout=20, **_proxy_kwargs())
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            except requests.exceptions.HTTPError:
                raise
            except Exception:
                pass

        resp = requests.get(url, headers=headers, timeout=15, **_proxy_kwargs())
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    # No proxy configured; re-raise the last error from phase 1
    if last_error:
        raise last_error
    raise RuntimeError("Failed to fetch URL")


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
