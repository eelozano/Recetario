"""Unit tests for the recipe-scrapers → RecipeInput mapping (no network)."""

from __future__ import annotations

import pytest

from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType
from recetario.infrastructure.scraping import html_to_text, scraped_to_recipe_input


class FakeScraper:
    """Mimics the duck-typed surface recipe-scrapers exposes."""

    def __init__(self, *, title="", ingredients=None, instructions=None, yields=None,
                 instructions_list=None):
        self._title = title
        self._ingredients = ingredients
        self._instructions = instructions
        self._instructions_list = instructions_list
        self._yields = yields

    def title(self):
        return self._title

    def ingredients(self):
        if self._ingredients is None:
            raise ValueError("no ingredients")
        return self._ingredients

    def instructions(self):
        if self._instructions is None:
            raise ValueError("no instructions")
        return self._instructions

    def instructions_list(self):
        if self._instructions_list is None:
            raise ValueError("no instructions list")
        return self._instructions_list

    def yields(self):
        if self._yields is None:
            raise ValueError("no yields")
        return self._yields


def test_maps_title_ingredients_and_instructions():
    scraper = FakeScraper(
        title="  Garlic Soup  ",
        ingredients=["2 cloves garlic", " 1 tbsp olive oil ", ""],
        instructions="Step one.\n\nStep two.\n",
        yields="4 servings",
    )
    result = scraped_to_recipe_input(scraper, source_url="https://example.com/soup")

    assert result.title == "Garlic Soup"
    assert result.source_type == SourceType.WEB
    assert result.status == RecipeStatus.DRAFT
    assert result.source_url == "https://example.com/soup"
    assert result.servings == 4
    # Blank ingredient lines are dropped; raw line kept as both name and raw_text.
    assert [i.name for i in result.ingredients] == ["2 cloves garlic", "1 tbsp olive oil"]
    assert result.ingredients[0].raw_text == "2 cloves garlic"
    assert result.instructions_md == "Step one.\nStep two."


def test_prefers_instructions_list_when_present():
    scraper = FakeScraper(
        title="Toast",
        ingredients=["1 slice bread"],
        instructions_list=["Toast the bread.", " Butter it. "],
    )
    result = scraped_to_recipe_input(scraper, source_url=None)
    assert result.instructions_md == "Toast the bread.\nButter it."


def test_missing_instructions_yields_none():
    scraper = FakeScraper(title="Water", ingredients=["1 cup water"])
    result = scraped_to_recipe_input(scraper, source_url=None)
    assert result.instructions_md is None
    assert result.servings is None


def test_no_title_and_no_ingredients_raises():
    scraper = FakeScraper(title="", ingredients=[])
    with pytest.raises(ScrapeError):
        scraped_to_recipe_input(scraper, source_url="https://example.com/blog")


# --- Deterministic parse of a real schema.org/JSON-LD page (no network, no LLM) ---

# A minimal but realistic page: the recipe is expressed as JSON-LD, the form
# every major recipe site emits. recipe-scrapers reads this offline from the
# HTML string, proving a structured import needs neither network nor an API key.
_JSONLD_HTML = """<!doctype html>
<html><head><title>Garlic Soup</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Simple Garlic Soup",
  "recipeYield": "4 servings",
  "recipeIngredient": ["2 cloves garlic", "1 tbsp olive oil", "4 cups water"],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Saute the garlic in the oil."},
    {"@type": "HowToStep", "text": "Add water and simmer."}
  ]
}
</script></head><body><h1>Simple Garlic Soup</h1></body></html>
"""


def test_jsonld_html_parses_deterministically_without_llm():
    # Offline: scrape_html operates on the HTML string only — no fetch, no LLM.
    scrape_html = pytest.importorskip("recipe_scrapers").scrape_html
    scraper = scrape_html(_JSONLD_HTML, org_url="https://example.com/soup", wild_mode=True)
    result = scraped_to_recipe_input(scraper, source_url="https://example.com/soup")

    assert result.title == "Simple Garlic Soup"
    assert result.source_type == SourceType.WEB
    assert result.status == RecipeStatus.DRAFT
    assert result.servings == 4
    assert [i.name for i in result.ingredients] == [
        "2 cloves garlic",
        "1 tbsp olive oil",
        "4 cups water",
    ]
    assert result.instructions_md == "Saute the garlic in the oil.\nAdd water and simmer."


# --- html_to_text (the LLM-fallback page cleaner) ---


def test_html_to_text_strips_chrome_and_keeps_visible_text():
    html = """<html><head><style>.x{color:red}</style>
    <script>var a = 1;</script></head>
    <body><nav>Home</nav><h1>Garlic Soup</h1>
    <p>2 cloves garlic</p><noscript>enable js</noscript></body></html>"""
    text = html_to_text(html)

    assert "Garlic Soup" in text
    assert "2 cloves garlic" in text
    assert "Home" in text  # nav text is kept; only script/style/noscript are dropped
    assert "color:red" not in text
    assert "var a" not in text
    assert "enable js" not in text
    # No blank lines survive the collapse.
    assert "\n\n" not in text
