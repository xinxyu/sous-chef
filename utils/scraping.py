"""Fallback recipe/ingredient parsing when recipe-scrapers fails."""
import json
import re
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Browser-like headers to reduce 403 from sites like AllRecipes
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def _parse_ingredients_from_soup(soup: BeautifulSoup) -> list[str]:
    """Parse ingredients from a BeautifulSoup instance."""
    ingredients = []

    # Pattern 1: JSON-LD
    json_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_scripts:
        try:
            script_content = script.string
            if not script_content:
                continue
            data = json.loads(script_content)
            recipe_data = None
            if isinstance(data, dict):
                recipe_data = data
            elif isinstance(data, list):
                recipe_data = next(
                    (item for item in data if item is not None and isinstance(item, dict) and item.get("@type") == "Recipe"),
                    None,
                )
            if recipe_data is None or not isinstance(recipe_data, dict):
                continue
            if recipe_data.get("@type") != "Recipe" or "recipeIngredient" not in recipe_data:
                continue
            ingredients_raw = recipe_data["recipeIngredient"]
            if not isinstance(ingredients_raw, list):
                continue
            processed_ingredients = []
            for ing in ingredients_raw:
                if ing is None:
                    continue
                if isinstance(ing, str):
                    processed_ingredients.append(ing.strip())
                elif isinstance(ing, dict):
                    parts = []
                    if "amount" in ing:
                        parts.append(str(ing["amount"]))
                    if "unit" in ing:
                        parts.append(str(ing["unit"]))
                    if "name" in ing:
                        parts.append(str(ing["name"]))
                    elif "ingredient" in ing:
                        parts.append(str(ing["ingredient"]))
                    if parts:
                        processed_ingredients.append(" ".join(parts).strip())
                else:
                    processed_ingredients.append(str(ing).strip())
            ingredients = [ing for ing in processed_ingredients if ing]
            if ingredients:
                logger.info(f"Found {len(ingredients)} ingredients from JSON-LD")
                break
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
            continue

    # Pattern 2: data-ingredient-name
    if not ingredients:
        ingredient_elements = soup.find_all(["span", "li"], {"data-ingredient-name": True})
        if ingredient_elements:
            for elem in ingredient_elements:
                parent = elem.find_parent("li")
                if parent:
                    ingredient_text = parent.get_text(separator=" ", strip=True)
                else:
                    ingredient_text = elem.get_text(separator=" ", strip=True)
                ingredient_text = re.sub(r"\s+", " ", ingredient_text).strip()
                if ingredient_text and len(ingredient_text) > 2:
                    ingredients.append(ingredient_text)
            if ingredients:
                logger.info("Found ingredients from data-ingredient-name")

    # Pattern 3: AllRecipes selectors
    if not ingredients:
        allrecipes_selectors = [
                "li.mntl-structured-ingredients__list-item",
                "li.ingredients-section__list-item",
                "li[data-testid='ingredient-item']",
                ".mntl-structured-ingredients__list-item",
                ".ingredients-section__list-item",
                "[data-testid='ingredient-item']",
                "li[data-ingredient-name]",
                "span[data-ingredient-name]",
        ]
        for selector in allrecipes_selectors:
            elements = soup.select(selector)
            if elements:
                for elem in elements:
                    if elem.name == "span":
                        parent_li = elem.find_parent("li")
                        text = parent_li.get_text(separator=" ", strip=True) if parent_li else elem.get_text(separator=" ", strip=True)
                    else:
                        text = elem.get_text(separator=" ", strip=True)
                    text = re.sub(r"\s+", " ", text).strip()
                    if text and len(text) > 2:
                        ingredients.append(text)
                if ingredients:
                    logger.info(f"Found ingredients using selector: {selector}")
                    break

    # Pattern 4: Common selectors
    if not ingredients:
        selectors = [
                "li.ingredients-item",
                "li.ingredient",
                "li[itemprop='recipeIngredient']",
                ".recipe-ingredients li",
                ".ingredients-list li",
                "ul.ingredients li",
                "div.ingredients li",
                ".ingredients-item",
                ".ingredient",
                "[itemprop='recipeIngredient']",
        ]
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                for elem in elements:
                    if elem.name == "li":
                        text = elem.get_text(separator=" ", strip=True)
                    else:
                        parent_li = elem.find_parent("li")
                        text = parent_li.get_text(separator=" ", strip=True) if parent_li else elem.get_text(separator=" ", strip=True)
                    if text and len(text) > 2:
                        ingredients.append(text)
                if ingredients:
                    logger.info(f"Found ingredients using selector: {selector}")
                    break

    # Pattern 5: Heading-based
    if not ingredients:
        headings = soup.find_all(["h2", "h3"], string=re.compile(r"ingredients", re.I))
        for heading in headings:
            next_elem = heading.find_next_sibling()
            while next_elem and len(ingredients) == 0:
                if next_elem.name == "ul" or (next_elem.name == "div" and next_elem.find("ul")):
                    list_container = next_elem if next_elem.name == "ul" else next_elem.find("ul")
                    list_items = list_container.find_all("li", recursive=False) or list_container.find_all("li", recursive=True)
                    for li in list_items:
                        text = li.get_text(separator=" ", strip=True)
                        text = re.sub(r"\s+", " ", text).strip()
                        if text and len(text) > 2 and not re.match(r"^[\d\s/]+$", text) and len(text) > 5:
                            ingredients.append(text)
                    if ingredients:
                        logger.info("Found ingredients from heading-based search")
                        break
                next_elem = next_elem.find_next_sibling()
            if ingredients:
                break

    # Pattern 6: Ingredient sections
    if not ingredients:
        ingredient_sections = soup.find_all(["section", "div"], class_=re.compile(r"ingredient", re.I))
        for section in ingredient_sections:
            for li in section.find_all("li"):
                text = li.get_text(strip=True)
                if text and len(text) > 2 and not re.match(r"^[^\w]*$", text):
                    ingredients.append(text)

    logger.info(f"Fallback parser found {len(ingredients)} ingredients")
    return ingredients


def fallback_parse_ingredients(url: str) -> list[str]:
    """Parse ingredients from HTML when recipe-scrapers fails. Fetches the URL."""
    try:
        response = requests.get(url, headers=_DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        return _parse_ingredients_from_soup(soup)
    except Exception as e:
        logger.error(f"Error in fallback ingredient parsing: {str(e)}")
        return []


def fallback_parse_ingredients_from_html(html: str) -> list[str]:
    """Parse ingredients from pre-fetched HTML. Use when you already have the page content."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return _parse_ingredients_from_soup(soup)
    except Exception as e:
        logger.error(f"Error parsing ingredients from HTML: {str(e)}")
        return []


def fallback_parse_recipe_from_html(html: str, url: str = "") -> dict | None:
    """Parse full recipe from pre-fetched HTML."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return _parse_full_recipe_from_soup(soup, url)
    except Exception as e:
        logger.error(f"Error parsing recipe from HTML: {str(e)}")
        return None


def _parse_full_recipe_from_soup(soup: BeautifulSoup, url: str = "") -> dict | None:
    """Extract full recipe from BeautifulSoup. Returns dict or None."""
    title = ""
    ingredients: list[str] = []
    instructions: list[str] = []

    # JSON-LD Recipe
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "Recipe":
                    continue
                if not title and item.get("name"):
                    title = str(item["name"]).strip()
                if not ingredients and "recipeIngredient" in item:
                    raw = item["recipeIngredient"]
                    if isinstance(raw, list):
                        for ing in raw:
                            if isinstance(ing, str):
                                ingredients.append(ing.strip())
                            elif isinstance(ing, dict):
                                parts = []
                                if ing.get("amount"):
                                    parts.append(str(ing["amount"]))
                                if ing.get("unit"):
                                    parts.append(str(ing["unit"]))
                                if ing.get("name"):
                                    parts.append(str(ing["name"]))
                                elif ing.get("ingredient"):
                                    parts.append(str(ing["ingredient"]))
                                if parts:
                                    ingredients.append(" ".join(parts).strip())
                if not instructions and "recipeInstructions" in item:
                    raw = item["recipeInstructions"]
                    if isinstance(raw, list):
                        for step in raw:
                            if isinstance(step, str):
                                instructions.append(step.strip())
                            elif isinstance(step, dict) and step.get("text"):
                                instructions.append(str(step["text"]).strip())
                    elif isinstance(raw, str):
                        instructions = [s.strip() for s in raw.split("\n") if s.strip()]
                if title and ingredients:
                    break
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    if not ingredients:
        ingredients = _parse_ingredients_from_soup(soup)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                title = og["content"]

    if title or ingredients or instructions:
        return {
            "title": title or "",
            "ingredients": ingredients,
            "instructions": instructions,
            "total_time": None,
            "yields": "",
            "image": "",
            "host": "",
            "nutrients": None,
        }
    return None


def fallback_parse_recipe(url: str) -> dict | None:
    """Parse full recipe from URL. Fetches the page."""
    try:
        response = requests.get(url, headers=_DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        return _parse_full_recipe_from_soup(soup, url)
    except Exception as e:
        logger.error(f"Error in fallback recipe parsing: {str(e)}")
        return None
