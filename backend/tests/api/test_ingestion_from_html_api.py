"""API tests for the in-app-browser import path (`POST /ingestion/jobs/from-html`).

The scraper is faked via `app.state.scraper_factory`, so no network is touched
and no real recipe-scrapers parse runs. Starlette runs BackgroundTasks
synchronously within the TestClient request, so by the time `client.post(...)`
returns, the job has already reached a terminal state.
"""

from __future__ import annotations

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType


class _StubScraper:
    """Fake RecipeScraper whose `parse_html` returns a draft or raises."""

    def __init__(self, result: RecipeInput | None = None, error: str | None = None):
        self._result = result
        self._error = error
        self.seen_html: str | None = None

    def parse_html(self, html: str, url: str) -> RecipeInput:
        self.seen_html = html
        if self._error is not None:
            raise ScrapeError(self._error)
        assert self._result is not None
        return self._result

    def scrape(self, url: str) -> RecipeInput:  # pragma: no cover - unused here
        raise AssertionError("from-html path must not fetch via scrape()")


def _draft() -> RecipeInput:
    return RecipeInput(
        title="Captured Stew",
        source_url="https://example.com/stew",
        source_type=SourceType.WEB,
        status=RecipeStatus.DRAFT,
        instructions_md="Simmer.\nServe.",
        ingredients=[
            RecipeIngredientInput(name="1 onion", raw_text="1 onion"),
        ],
    )


def test_from_html_creates_draft_recipe(client):
    stub = _StubScraper(result=_draft())
    client.app.state.scraper_factory = lambda: stub

    resp = client.post(
        "/ingestion/jobs/from-html",
        json={"url": "https://example.com/stew", "html": "<html>rendered</html>"},
    )
    assert resp.status_code == 202, resp.text
    job = resp.json()
    assert job["input_type"] == "web"
    job_id = job["id"]

    polled = client.get(f"/ingestion/jobs/{job_id}").json()
    assert polled["status"] == "succeeded"
    assert polled["progress"] == 100
    recipe_id = polled["result_recipe_id"]
    assert recipe_id is not None

    # The provided HTML — not a fetched page — was what got parsed.
    assert stub.seen_html == "<html>rendered</html>"

    recipe = client.get(f"/recipes/{recipe_id}").json()
    assert recipe["title"] == "Captured Stew"
    assert recipe["status"] == "draft"
    assert recipe["source_type"] == "web"
    assert recipe["ingredients"][0]["name"] == "1 onion"


def test_from_html_records_friendly_failure_without_llm_fallback(client):
    # conftest leaves the extractor disabled, so there's no LLM fallback. A parse
    # miss must surface the clean, user-facing message — not the raw error.
    client.app.state.scraper_factory = lambda: _StubScraper(error="boom: no JSON-LD")

    resp = client.post(
        "/ingestion/jobs/from-html",
        json={"url": "https://example.com/blog", "html": "<html>no recipe</html>"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    polled = client.get(f"/ingestion/jobs/{job_id}").json()
    assert polled["status"] == "failed"
    assert polled["result_recipe_id"] is None
    assert "Couldn't read a recipe" in polled["error"]
    assert "+ New recipe" in polled["error"]
    assert "JSON-LD" not in polled["error"]


class _FallbackExtractor:
    """Stands in for the LLM fallback; records the page text it was handed."""

    def __init__(self) -> None:
        self.web_calls: list[str] = []

    def extract_from_web(self, page_text: str, *, source_url):
        self.web_calls.append(page_text)
        return RecipeInput(
            title="Stew (from text)",
            source_url=source_url,
            source_type=SourceType.WEB,
            status=RecipeStatus.DRAFT,
            ingredients=[RecipeIngredientInput(name="onion", raw_text="1 onion")],
        )


def test_from_html_falls_back_to_llm_over_captured_html(client):
    # Deterministic parse finds nothing, but an extractor IS configured: the LLM
    # fallback runs over the *captured* HTML's text (no network fetch).
    client.app.state.scraper_factory = lambda: _StubScraper(error="no JSON-LD")
    extractor = _FallbackExtractor()
    client.app.state.extractor_factory = lambda: extractor

    resp = client.post(
        "/ingestion/jobs/from-html",
        json={
            "url": "https://example.com/blog",
            "html": "<html><body>Best Stew\n1 onion\nSimmer.</body></html>",
        },
    )
    assert resp.status_code == 202, resp.text
    polled = client.get(f"/ingestion/jobs/{resp.json()['id']}").json()
    assert polled["status"] == "succeeded", polled

    recipe = client.get(f"/recipes/{polled['result_recipe_id']}").json()
    assert recipe["title"] == "Stew (from text)"
    # The fallback ran exactly once, over text derived from the captured HTML.
    assert len(extractor.web_calls) == 1
    assert "Best Stew" in extractor.web_calls[0]
    assert "<body>" not in extractor.web_calls[0]  # markup stripped to text


def test_from_html_requires_url_and_html(client):
    # Both fields are required and non-empty (min_length=1) → 422.
    assert (
        client.post("/ingestion/jobs/from-html", json={"url": "https://x.com"}).status_code
        == 422
    )
    assert (
        client.post(
            "/ingestion/jobs/from-html", json={"url": "https://x.com", "html": ""}
        ).status_code
        == 422
    )
