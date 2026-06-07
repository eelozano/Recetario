"""Deterministic web-recipe scraper (implements the RecipeScraper port).

Built on the `recipe-scrapers` library, which reads schema.org/JSON-LD `Recipe`
metadata (and site-specific extractors) — free, fast, and accurate for the common
case. No LLM involved; the produced recipe is a *draft* the user reviews.

The HTTP fetch lives in `RecipeScrapersAdapter.scrape`; the scraper-object → DTO
mapping is the pure `scraped_to_recipe_input`, so it is unit-tested against a fake
scraper with no network.
"""

from __future__ import annotations

import re
from typing import Any

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType

_SERVINGS_RE = re.compile(r"\d+")


def _safe(call: Any) -> Any:
    """recipe-scrapers raises on missing fields; treat any failure as 'absent'."""
    try:
        return call()
    except Exception:
        return None


def _parse_servings(yields: Any) -> int | None:
    if not yields:
        return None
    match = _SERVINGS_RE.search(str(yields))
    return int(match.group()) if match else None


def _instruction_steps(scraper: Any) -> list[str]:
    # Prefer the pre-split list; fall back to a newline-joined blob.
    steps = _safe(getattr(scraper, "instructions_list", lambda: None))
    if isinstance(steps, list) and steps:
        return [s.strip() for s in steps if isinstance(s, str) and s.strip()]
    blob = _safe(getattr(scraper, "instructions", lambda: None))
    if isinstance(blob, str):
        return [line.strip() for line in blob.splitlines() if line.strip()]
    return []


def scraped_to_recipe_input(scraper: Any, *, source_url: str | None) -> RecipeInput:
    """Map a recipe-scrapers scraper object into a draft RecipeInput.

    Raises ScrapeError if the page yielded neither a title nor ingredients — i.e.
    there was no recipe to import.
    """
    title = _safe(getattr(scraper, "title", lambda: None))
    title = title.strip() if isinstance(title, str) else ""

    raw_ingredients = _safe(getattr(scraper, "ingredients", lambda: None)) or []
    lines = [s.strip() for s in raw_ingredients if isinstance(s, str) and s.strip()]

    if not title and not lines:
        raise ScrapeError("No recipe found at this URL (no title or ingredients).")

    steps = _instruction_steps(scraper)
    instructions_md = "\n".join(steps) if steps else None

    # Deterministic scraping yields raw ingredient strings; quantity/unit parsing
    # is deferred to the LLM slice. We keep the raw line as both name and raw_text
    # so the draft is reviewable, then the user (or Claude) refines it.
    ingredients = [RecipeIngredientInput(name=line, raw_text=line) for line in lines]

    return RecipeInput(
        title=title or "Untitled recipe",
        source_url=source_url,
        source_type=SourceType.WEB,
        servings=_parse_servings(_safe(getattr(scraper, "yields", lambda: None))),
        status=RecipeStatus.DRAFT,
        instructions_md=instructions_md,
        ingredients=ingredients,
    )


# Browser-like headers — many recipe sites 403 the default httpx/python agent.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class RecipeScrapersAdapter:
    """Fetches and parses a recipe URL via the recipe-scrapers library.

    We fetch the HTML ourselves (httpx) and hand it to `scrape_html` in
    `wild_mode`, so generic schema.org/JSON-LD parsing covers sites without a
    dedicated recipe-scrapers extractor.
    """

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def scrape(self, url: str) -> RecipeInput:
        # Lazy import so the dependency is only needed when actually scraping
        # (tests inject a fake scraper and never reach this path).
        try:
            import httpx
            from recipe_scrapers import scrape_html
        except ImportError as exc:  # pragma: no cover - import guard
            raise ScrapeError(
                "recipe-scrapers is not installed; run `pip install recipe-scrapers`."
            ) from exc

        try:
            resp = httpx.get(
                url,
                follow_redirects=True,
                timeout=self._timeout,
                headers=_BROWSER_HEADERS,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise ScrapeError(f"Could not fetch {url}: {exc}") from exc

        try:
            scraper = scrape_html(resp.text, org_url=url, wild_mode=True)
        except Exception as exc:
            raise ScrapeError(f"Could not parse a recipe from {url}: {exc}") from exc

        return scraped_to_recipe_input(scraper, source_url=url)

    def fetch_page_text(self, url: str) -> str:
        """Fetch a page and return its visible text (markup stripped).

        Used only as the LLM fallback when deterministic scraping fails — we hand
        this text to the extractor. Kept separate from `scrape` so the happy path
        never pays for HTML→text cleaning. Raises ScrapeError on a fetch failure.
        """
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - import guard
            raise ScrapeError("httpx is not installed.") from exc

        try:
            resp = httpx.get(
                url,
                follow_redirects=True,
                timeout=self._timeout,
                headers=_BROWSER_HEADERS,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise ScrapeError(f"Could not fetch {url}: {exc}") from exc

        return html_to_text(resp.text)


def html_to_text(html: str) -> str:
    """Reduce an HTML document to its visible text.

    Prefers BeautifulSoup (a transitive recipe-scrapers dependency) to drop
    script/style/nav chrome; falls back to a crude tag strip if it is somehow
    unavailable. Pure and offline, so it is unit-tested directly.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - fallback path
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    # Collapse runs of blank lines so the LLM sees compact, readable text.
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
