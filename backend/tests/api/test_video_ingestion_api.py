"""API tests for the video (captions → LLM) ingestion path.

The transcript fetcher, LLM extractor, and FDC provider are all faked via
app.state factories, so no network, yt-dlp, or Anthropic SDK is touched. Starlette
runs BackgroundTasks synchronously, so the job is terminal once `post` returns.
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
from recetario.application.ports import TranscriptError
from recetario.domain.entities import RecipeStatus, SourceType

_VIDEO_URL = "https://www.youtube.com/watch?v=abc123"


class _StubFetcher:
    def __init__(self, transcript: str = "today we make garlic soup", error: str | None = None):
        self._transcript = transcript
        self._error = error

    def fetch_transcript(self, url: str) -> str:
        if self._error is not None:
            raise TranscriptError(self._error)
        return self._transcript


class _StubExtractor:
    def extract_from_transcript(self, transcript: str, *, source_url: str | None) -> RecipeInput:
        return RecipeInput(
            title="Garlic Soup",
            source_url=source_url,
            source_type=SourceType.VIDEO,
            status=RecipeStatus.DRAFT,
            servings=4,
            instructions_md="Sauté garlic.\nSimmer.",
            ingredients=[
                RecipeIngredientInput(
                    name="garlic",
                    quantity=Decimal("2"),
                    unit="clove",
                    raw_text="two cloves of garlic",
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
            nutrients=[
                FoodNutrient(usda_nutrient_id=1008, name="calories", unit="kcal", amount=Decimal("149"))
            ],
        )


def test_video_ingestion_creates_draft(client):
    client.app.state.video_fetcher_factory = lambda: _StubFetcher()
    client.app.state.extractor_factory = lambda: _StubExtractor()
    # No provider → enrichment skipped, but video extraction still works.

    resp = client.post("/ingestion/jobs", json={"url": _VIDEO_URL})
    assert resp.status_code == 202, resp.text
    job = resp.json()
    assert job["input_type"] == "video"  # auto-detected from the YouTube host

    polled = client.get(f"/ingestion/jobs/{job['id']}").json()
    assert polled["status"] == "succeeded"
    recipe = client.get(f"/recipes/{polled['result_recipe_id']}").json()
    assert recipe["title"] == "Garlic Soup"
    assert recipe["source_type"] == "video"
    assert recipe["source_url"] == _VIDEO_URL
    assert recipe["ingredients"][0]["name"] == "garlic"
    assert recipe["ingredients"][0]["usda_fdc_id"] is None  # no provider → unlinked


def test_video_ingestion_enriches_with_provider(client):
    client.app.state.video_fetcher_factory = lambda: _StubFetcher()
    client.app.state.extractor_factory = lambda: _StubExtractor()
    client.app.state.nutrition_provider_factory = lambda: _StubProvider()

    resp = client.post("/ingestion/jobs", json={"url": _VIDEO_URL})
    polled = client.get(f"/ingestion/jobs/{resp.json()['id']}").json()
    assert polled["status"] == "succeeded"
    ing = client.get(f"/recipes/{polled['result_recipe_id']}").json()["ingredients"][0]
    assert ing["usda_fdc_id"] == 1104647
    assert Decimal(str(ing["gram_weight"])) == Decimal("6")


def test_video_ingestion_fails_without_extractor(client):
    # conftest disables the extractor by default → video import cannot proceed.
    client.app.state.video_fetcher_factory = lambda: _StubFetcher()

    resp = client.post("/ingestion/jobs", json={"url": _VIDEO_URL})
    polled = client.get(f"/ingestion/jobs/{resp.json()['id']}").json()
    assert polled["status"] == "failed"
    assert polled["result_recipe_id"] is None
    assert "Anthropic" in polled["error"]


def test_video_ingestion_records_transcript_failure(client):
    client.app.state.video_fetcher_factory = lambda: _StubFetcher(error="No captions available")
    client.app.state.extractor_factory = lambda: _StubExtractor()

    resp = client.post("/ingestion/jobs", json={"url": _VIDEO_URL})
    polled = client.get(f"/ingestion/jobs/{resp.json()['id']}").json()
    assert polled["status"] == "failed"
    assert "No captions available" in polled["error"]


def test_explicit_input_type_overrides_detection(client):
    # A non-video URL forced to video still routes through the video pipeline.
    client.app.state.video_fetcher_factory = lambda: _StubFetcher()
    client.app.state.extractor_factory = lambda: _StubExtractor()

    resp = client.post(
        "/ingestion/jobs",
        json={"url": "https://example.com/some-page", "input_type": "video"},
    )
    job = resp.json()
    assert job["input_type"] == "video"
    polled = client.get(f"/ingestion/jobs/{job['id']}").json()
    assert polled["status"] == "succeeded"
