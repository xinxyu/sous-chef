"""Tests for the fallback ingredient parser (utils.scraping.fallback_parse_ingredients)."""

import json
import pytest
from unittest.mock import patch, MagicMock

from utils.scraping import fallback_parse_ingredients


def _make_html_with_json_ld(ingredients: list[str]) -> bytes:
    """Build minimal HTML that the parser reads (JSON-LD Recipe)."""
    ld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Test Recipe",
        "recipeIngredient": ingredients,
    }
    script_content = json.dumps(ld)
    html = f"""<!DOCTYPE html><html><head>
    <script type="application/ld+json">{script_content}</script>
    </head><body></body></html>"""
    return html.encode("utf-8")


class TestFallbackParseIngredients:
    """Unit tests with mocked HTTP (no network)."""

    @patch("utils.scraping.requests.get")
    def test_returns_ingredients_from_json_ld(self, mock_get: MagicMock) -> None:
        expected = [
            "1 lb fettuccine pasta",
            "1/2 cup butter",
            "1 pint heavy cream",
            "1 cup grated parmesan",
            "2 cloves garlic",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = _make_html_with_json_ld(expected)
        mock_get.return_value = mock_resp

        result = fallback_parse_ingredients("https://example.com/recipe")

        assert len(result) == len(expected)
        assert result == expected
        mock_get.assert_called_once()

    @patch("utils.scraping.requests.get")
    def test_count_and_contents(self, mock_get: MagicMock) -> None:
        ingredients = [
            "1 lb fettuccine",
            "1/2 cup butter",
            "1 pint cream",
            "1 cup parmesan",
            "2 cloves garlic",
            "salt and pepper",
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = _make_html_with_json_ld(ingredients)
        mock_get.return_value = mock_resp

        result = fallback_parse_ingredients("https://example.com/recipe")

        assert len(result) >= 6
        combined = " ".join(result).lower()
        for keyword in ("fettuccine", "butter", "cream", "parmesan"):
            assert keyword in combined, f"Expected '{keyword}' in ingredients"

    @patch("utils.scraping.requests.get")
    def test_returns_empty_list_when_no_recipe_in_html(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"<!DOCTYPE html><html><body><p>No recipe here</p></body></html>"
        mock_get.return_value = mock_resp

        result = fallback_parse_ingredients("https://example.com/page")

        assert result == []

    @patch("utils.scraping.requests.get")
    def test_returns_empty_list_on_http_error(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("Connection error")

        result = fallback_parse_ingredients("https://example.com/recipe")

        assert result == []


@pytest.mark.integration
def test_fallback_parse_ingredients_live_allrecipes() -> None:
    """Integration test: real AllRecipes URL (run explicitly when needed)."""
    url = "https://www.allrecipes.com/recipe/23431/to-die-for-fettuccine-alfredo/"
    ingredients = fallback_parse_ingredients(url)

    assert len(ingredients) >= 6, f"Expected at least 6 ingredients, got {len(ingredients)}"
    combined = " ".join(ingredients).lower()
    for keyword in ("24 ounces dry fettuccine pasta", "1 cup butter", "¾ cup grated romano cheese", "parmesan"):
        assert keyword in combined, f"Expected '{keyword}' in ingredients but got {combined}"
