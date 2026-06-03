"""API test for the optional LLM enrichment path of URL ingestion.

Both the extractor and the live FDC provider are faked via app.state factories,
so no network or Anthropic SDK is touched. The deterministic scraper is faked as
in test_ingestion_api.py; here we additionally inject the enrichment seam.
"""

from __future__ import annotations

from decimal import Decimal

from recetario.application.dto import (
    FoodDetail,
    FoodNutrient,
    RecipeIngredientInput,
    RecipeInput,
    ResolvedIngredient,
)
from recetario.domain.entities import RecipeStatus, SourceType


class _StubScraper:
    def scrape(self, url: str) -> RecipeInput:
        return RecipeInput(
            title="Garlic Soup",
            source_url=url,
            source_type=SourceType.WEB,
            status=RecipeStatus.DRAFT,
            ingredients=[
                RecipeIngredientInput(name="2 cloves garlic", raw_text="2 cloves garlic"),
            ],
        )


class _StubExtractor:
    def structure(self, draft: RecipeInput) -> RecipeInput:
        return RecipeInput(
            title=draft.title,
            source_url=draft.source_url,
            source_type=draft.source_type,
            status=draft.status,
            ingredients=[
                RecipeIngredientInput(
                    name="garlic",
                    quantity=Decimal("2"),
                    unit="clove",
                    raw_text="2 cloves garlic",
                )
            ],
        )

    def resolve_nutrition(self, ingredients, search):
        return [
            ResolvedIngredient(index=0, fdc_id=1104647, gram_weight=Decimal("6"), confidence=0.95)
        ]


class _StubProvider:
    def search(self, query, *, page_size=5):
        return []

    def get_food(self, fdc_id):
        return FoodDetail(
            fdc_id=fdc_id,
            description="Garlic, raw",
            data_type="SR Legacy",
            nutrients=[FoodNutrient(usda_nutrient_id=1008, name="calories", unit="kcal", amount=Decimal("149"))],
        )


def test_ingest_url_enriches_draft_when_extractor_configured(client):
    client.app.state.scraper_factory = _StubScraper
    client.app.state.extractor_factory = lambda: _StubExtractor()
    client.app.state.nutrition_provider_factory = lambda: _StubProvider()

    resp = client.post("/ingestion/jobs", json={"url": "https://example.com/soup"})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["id"]

    polled = client.get(f"/ingestion/jobs/{job_id}").json()
    assert polled["status"] == "succeeded"
    recipe_id = polled["result_recipe_id"]

    recipe = client.get(f"/recipes/{recipe_id}").json()
    ing = recipe["ingredients"][0]
    assert ing["name"] == "garlic"
    assert Decimal(str(ing["quantity"])) == Decimal("2")
    assert ing["unit"] == "clove"
    assert ing["usda_fdc_id"] == 1104647
    assert Decimal(str(ing["gram_weight"])) == Decimal("6")


def test_ingest_url_skips_enrichment_without_provider(client):
    # Extractor present but no FDC provider → enrichment is skipped entirely,
    # leaving the deterministic scraped draft untouched.
    client.app.state.scraper_factory = _StubScraper
    client.app.state.extractor_factory = lambda: _StubExtractor()
    client.app.state.nutrition_provider_factory = lambda: None

    resp = client.post("/ingestion/jobs", json={"url": "https://example.com/soup"})
    job_id = resp.json()["id"]

    polled = client.get(f"/ingestion/jobs/{job_id}").json()
    assert polled["status"] == "succeeded"
    recipe = client.get(f"/recipes/{polled['result_recipe_id']}").json()
    ing = recipe["ingredients"][0]
    assert ing["name"] == "2 cloves garlic"
    assert ing["usda_fdc_id"] is None
