"""API tests for the ingestion endpoints.

The scraper is faked via `app.state.scraper_factory`, so no network is touched.
Starlette runs BackgroundTasks synchronously within the TestClient request, so by
the time `client.post(...)` returns, the job has already reached a terminal state.
"""

from __future__ import annotations

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType


class _StubScraper:
    def __init__(self, result: RecipeInput | None = None, error: str | None = None):
        self._result = result
        self._error = error

    def scrape(self, url: str) -> RecipeInput:
        if self._error is not None:
            raise ScrapeError(self._error)
        assert self._result is not None
        return self._result


def _draft() -> RecipeInput:
    return RecipeInput(
        title="Scraped Soup",
        source_url="https://example.com/soup",
        source_type=SourceType.WEB,
        status=RecipeStatus.DRAFT,
        instructions_md="Boil.\nServe.",
        ingredients=[
            RecipeIngredientInput(name="2 cloves garlic", raw_text="2 cloves garlic"),
        ],
    )


def test_ingest_url_creates_draft_recipe(client):
    client.app.state.scraper_factory = lambda: _StubScraper(result=_draft())

    resp = client.post("/ingestion/jobs", json={"url": "https://example.com/soup"})
    assert resp.status_code == 202, resp.text
    job = resp.json()
    job_id = job["id"]

    # Background task already ran: poll the job and assert success.
    polled = client.get(f"/ingestion/jobs/{job_id}").json()
    assert polled["status"] == "succeeded"
    assert polled["progress"] == 100
    recipe_id = polled["result_recipe_id"]
    assert recipe_id is not None

    recipe = client.get(f"/recipes/{recipe_id}").json()
    assert recipe["title"] == "Scraped Soup"
    assert recipe["status"] == "draft"
    assert recipe["source_type"] == "web"
    assert recipe["instructions_md"] == "Boil.\nServe."
    assert recipe["ingredients"][0]["name"] == "2 cloves garlic"


def test_ingest_url_records_failure_on_scrape_error(client):
    client.app.state.scraper_factory = lambda: _StubScraper(error="No recipe found")

    resp = client.post("/ingestion/jobs", json={"url": "https://example.com/blog"})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    polled = client.get(f"/ingestion/jobs/{job_id}").json()
    assert polled["status"] == "failed"
    assert polled["result_recipe_id"] is None
    assert "No recipe found" in polled["error"]


def test_list_jobs_and_missing_job(client):
    client.app.state.scraper_factory = lambda: _StubScraper(result=_draft())
    client.post("/ingestion/jobs", json={"url": "https://example.com/soup"})

    listing = client.get("/ingestion/jobs").json()
    assert len(listing) == 1
    assert listing[0]["input_url"] == "https://example.com/soup"

    assert client.get("/ingestion/jobs/999").status_code == 404
