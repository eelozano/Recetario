"""Unit tests for the recipe-scrapers → RecipeInput mapping (no network)."""

from __future__ import annotations

import pytest

from decimal import Decimal

from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType
from recetario.infrastructure.scraping import (
    html_to_text,
    macros_from_nutrients,
    scraped_to_recipe_input,
)


class FakeScraper:
    """Mimics the duck-typed surface recipe-scrapers exposes."""

    def __init__(self, *, title="", ingredients=None, instructions=None, yields=None,
                 instructions_list=None, nutrients=None):
        self._title = title
        self._ingredients = ingredients
        self._instructions = instructions
        self._instructions_list = instructions_list
        self._yields = yields
        self._nutrients = nutrients

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

    def nutrients(self):
        # recipe-scrapers raises NotImplementedError when a site has no nutrition;
        # mirror that so the mapper's _safe wrapper is exercised.
        if self._nutrients is None:
            raise NotImplementedError("no nutrients")
        return self._nutrients


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
    # No nutrition block on the page → every macro field stays unset (#35).
    assert result.calories_per_serving is None
    assert result.protein_per_serving is None
    assert result.sodium_per_serving is None


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


# --- Pre-fill macros from the page's published nutrition (#35) ---


def test_macros_from_nutrients_normalizes_units():
    # A typical schema.org NutritionInformation block: calories in kcal, macros in
    # grams, sodium in milligrams. Values map straight onto our canonical units.
    macros = macros_from_nutrients(
        {
            "calories": "270 kcal",
            "proteinContent": "21 g",
            "fatContent": "10 g",
            "carbohydrateContent": "8 g",
            "fiberContent": "2 g",
            "sodiumContent": "310 mg",
        }
    )
    assert macros == {
        "calories_per_serving": Decimal("270"),
        "protein_per_serving": Decimal("21"),
        "fat_per_serving": Decimal("10"),
        "carbs_per_serving": Decimal("8"),
        "fiber_per_serving": Decimal("2"),
        "sodium_per_serving": Decimal("310"),
    }


def test_macros_from_nutrients_converts_sodium_grams_to_mg():
    # Sites that publish sodium in grams ("0.31 g") must land as 310 mg, not 0.31.
    macros = macros_from_nutrients({"sodiumContent": "0.31 g"})
    assert macros["sodium_per_serving"] == Decimal("310.00")


def test_macros_from_nutrients_converts_kilojoules_to_kcal():
    # EU/AU sites publish energy in kJ; storing 1130 as kcal would be ~4× wrong.
    macros = macros_from_nutrients({"calories": "1130 kJ"})
    assert macros["calories_per_serving"] == Decimal("270.1")  # 1130 / 4.184


def test_macros_from_nutrients_is_case_insensitive_on_keys():
    macros = macros_from_nutrients({"Calories": "200 kcal", "ProteinContent": "15 g"})
    assert macros["calories_per_serving"] == Decimal("200")
    assert macros["protein_per_serving"] == Decimal("15")


def test_macros_from_nutrients_skips_missing_and_garbage_values():
    macros = macros_from_nutrients(
        {
            "calories": "270 kcal",
            "proteinContent": "not a number",
            "fatContent": "",
            "cholesterolContent": "40 mg",  # not a field we track → ignored
            # carbs/fiber/sodium absent
        }
    )
    # Only the parseable, tracked field survives; the rest are simply omitted.
    assert macros == {"calories_per_serving": Decimal("270")}


def test_macros_from_nutrients_handles_non_dict():
    # _safe yields None when a site has no nutrition; never raises.
    assert macros_from_nutrients(None) == {}
    assert macros_from_nutrients("nutrition") == {}


def test_scraped_input_prefills_macros_from_nutrients():
    scraper = FakeScraper(
        title="Smoky Pork Chops",
        ingredients=["4 pork chops"],
        nutrients={"calories": "430 kcal", "proteinContent": "38 g", "sodiumContent": "0.62 g"},
    )
    result = scraped_to_recipe_input(scraper, source_url="https://example.com/chops")
    assert result.calories_per_serving == Decimal("430")
    assert result.protein_per_serving == Decimal("38")
    assert result.sodium_per_serving == Decimal("620.00")  # 0.62 g → mg
    # Fields the page didn't publish stay unset.
    assert result.fat_per_serving is None
    assert result.carbs_per_serving is None


def test_scraped_input_without_nutrients_leaves_macros_unset():
    # nutrients() raising NotImplementedError must degrade to a blank-macro draft.
    scraper = FakeScraper(title="Plain Toast", ingredients=["1 slice bread"])
    result = scraped_to_recipe_input(scraper, source_url=None)
    assert result.calories_per_serving is None
    assert result.protein_per_serving is None
    assert result.fat_per_serving is None
    assert result.carbs_per_serving is None
    assert result.fiber_per_serving is None
    assert result.sodium_per_serving is None


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
  ],
  "nutrition": {
    "@type": "NutritionInformation",
    "calories": "90 kcal",
    "proteinContent": "2 g",
    "sodiumContent": "480 mg"
  }
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
    # The page's nutrition block is read by recipe-scrapers and pre-filled (#35).
    assert result.calories_per_serving == Decimal("90")
    assert result.protein_per_serving == Decimal("2")
    assert result.sodium_per_serving == Decimal("480")


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
