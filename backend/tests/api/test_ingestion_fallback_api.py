"""API tests for the web-ingestion paths after the deterministic-first change (#17).

Two behaviours are covered, both offline (the scraper and extractor are faked via
app.state factories, so no network or Anthropic SDK is touched):

* A successful deterministic scrape is used as-is — the LLM is never called, even
  when an extractor is configured.
* When the deterministic scrape fails and an extractor IS configured, the worker
  falls back to LLM extraction from the page's text.

The no-fallback case (scrape fails, no extractor → friendly error) lives in
test_ingestion_api.py.
"""

from __future__ import annotations

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType


def _scraped_draft(url: str) -> RecipeInput:
    return RecipeInput(
        title="Garlic Soup",
        source_url=url,
        source_type=SourceType.WEB,
        status=RecipeStatus.DRAFT,
        ingredients=[
            RecipeIngredientInput(name="2 cloves garlic", raw_text="2 cloves garlic"),
        ],
    )


class _ScrapeOkScraper:
    def scrape(self, url: str) -> RecipeInput:
        return _scraped_draft(url)

    def fetch_page_text(self, url: str) -> str:  # pragma: no cover - must not be hit
        raise AssertionError("fetch_page_text must not run when scraping succeeds")


class _ScrapeFailsScraper:
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def scrape(self, url: str) -> RecipeInput:
        raise ScrapeError("no structured recipe data on this page")

    def fetch_page_text(self, url: str) -> str:
        self.fetched.append(url)
        return "Best Garlic Soup\nIngredients\n2 cloves garlic\nSteps\nBoil."


class _SpyExtractor:
    """Records whether any LLM pass was invoked, and stands in for the fallback."""

    def __init__(self) -> None:
        self.web_calls: list[str] = []

    def structure(self, draft):  # pragma: no cover - must not be hit on happy path
        raise AssertionError("structure() must not run on a successful scrape")

    def resolve_nutrition(self, ingredients, search):  # pragma: no cover
        raise AssertionError("resolve_nutrition() must not run on a successful scrape")

    def extract_from_web(self, page_text: str, *, source_url):
        self.web_calls.append(page_text)
        return RecipeInput(
            title="Garlic Soup (from text)",
            source_url=source_url,
            source_type=SourceType.WEB,
            status=RecipeStatus.DRAFT,
            instructions_md="Boil.",
            ingredients=[
                RecipeIngredientInput(name="garlic", raw_text="2 cloves garlic"),
            ],
        )


def test_successful_scrape_never_calls_the_llm(client):
    # An extractor IS configured, but a clean scrape must bypass it entirely.
    spy = _SpyExtractor()
    client.app.state.scraper_factory = _ScrapeOkScraper
    client.app.state.extractor_factory = lambda: spy

    resp = client.post("/ingestion/jobs", json={"url": "https://example.com/soup"})
    assert resp.status_code == 202, resp.text
    polled = client.get(f"/ingestion/jobs/{resp.json()['id']}").json()
    assert polled["status"] == "succeeded"

    recipe = client.get(f"/recipes/{polled['result_recipe_id']}").json()
    # Deterministic draft used verbatim — no LLM structuring/linking happened.
    assert recipe["title"] == "Garlic Soup"
    assert recipe["ingredients"][0]["name"] == "2 cloves garlic"
    assert recipe["ingredients"][0]["usda_fdc_id"] is None
    assert spy.web_calls == []


def test_scrape_failure_falls_back_to_llm_when_extractor_configured(client):
    scraper = _ScrapeFailsScraper()
    spy = _SpyExtractor()
    client.app.state.scraper_factory = lambda: scraper
    client.app.state.extractor_factory = lambda: spy

    resp = client.post("/ingestion/jobs", json={"url": "https://example.com/blog"})
    assert resp.status_code == 202, resp.text
    polled = client.get(f"/ingestion/jobs/{resp.json()['id']}").json()
    assert polled["status"] == "succeeded", polled

    recipe = client.get(f"/recipes/{polled['result_recipe_id']}").json()
    assert recipe["title"] == "Garlic Soup (from text)"
    assert recipe["source_type"] == "web"
    assert recipe["ingredients"][0]["name"] == "garlic"
    # The page text was fetched and handed to the LLM fallback exactly once.
    assert scraper.fetched == ["https://example.com/blog"]
    assert len(spy.web_calls) == 1
