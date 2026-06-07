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
from decimal import Decimal, InvalidOperation
from typing import Any

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports import ScrapeError
from recetario.domain.entities import RecipeStatus, SourceType

_SERVINGS_RE = re.compile(r"\d+")
# First number (int or decimal) in a free-text nutrient value like "270 kcal".
_NUTRIENT_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")
# 1 kcal = 4.184 kJ — used to coerce kilojoule energy values into our kcal field.
_KJ_PER_KCAL = Decimal("4.184")


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


def _nutrient_number(value: Any) -> Decimal | None:
    """Pull the leading number out of a free-text nutrient value ("310 mg" → 310)."""
    if not isinstance(value, str):
        return None
    match = _NUTRIENT_NUM_RE.search(value)
    if match is None:
        return None
    try:
        return Decimal(match.group())
    except InvalidOperation:
        return None


def _energy_kcal(value: Any) -> Decimal | None:
    """Parse a schema.org `calories` value into kcal.

    Values are usually "270 kcal"/"270 calories" (already kcal), but EU/AU sites
    publish kilojoules ("1130 kJ"); storing that raw would be wrong by ~4×, so we
    convert kJ → kcal rather than trust the bare number.
    """
    number = _nutrient_number(value)
    if number is None:
        return None
    lowered = value.lower()
    if "kj" in lowered or "kilojoule" in lowered:
        return (number / _KJ_PER_KCAL).quantize(Decimal("0.1"))
    return number


def _mass_to(value: Any, *, target: str) -> Decimal | None:
    """Parse a schema.org mass value (protein/fat/carbs/fiber/sodium) into `target`.

    `target` is the app's canonical unit for the field — "g" for the macros, "mg"
    for sodium. Sites split between e.g. "310 mg" and "0.31 g" for the same number,
    so we read the value's own unit and normalize. An unrecognized/absent unit is
    assumed to already be in `target` (the value is taken at face value).
    """
    number = _nutrient_number(value)
    if number is None:
        return None
    lowered = value.lower()
    if "mcg" in lowered or "µg" in lowered or "microgram" in lowered:
        grams = number / Decimal(1_000_000)
    elif "mg" in lowered or "milligram" in lowered:
        grams = number / Decimal(1000)
    elif "g" in lowered:  # gram(s) / "g"
        grams = number
    else:
        return number  # no unit to normalize against — trust the number as-is
    return grams if target == "g" else grams * Decimal(1000)


# schema.org NutritionInformation key (lowercased) → (RecipeInput field, parser).
_NUTRIENT_FIELDS: tuple[tuple[str, str, Any], ...] = (
    ("calories", "calories_per_serving", _energy_kcal),
    ("proteincontent", "protein_per_serving", lambda v: _mass_to(v, target="g")),
    ("fatcontent", "fat_per_serving", lambda v: _mass_to(v, target="g")),
    ("carbohydratecontent", "carbs_per_serving", lambda v: _mass_to(v, target="g")),
    ("fibercontent", "fiber_per_serving", lambda v: _mass_to(v, target="g")),
    ("sodiumcontent", "sodium_per_serving", lambda v: _mass_to(v, target="mg")),
)


def macros_from_nutrients(raw: Any) -> dict[str, Decimal]:
    """Map a recipe-scrapers `nutrients()` dict to our per-serving macro fields.

    schema.org `NutritionInformation` carries free-text values ("270 kcal",
    "0.31 g", "310 mg"); we normalize each to the app's canonical unit (kcal, g,
    g, g, g, mg). Every field is parsed independently and any miss is simply
    omitted, so partial or junk nutrition never breaks the import — the draft just
    lands with fewer (or no) macros pre-filled, exactly as before this feature.

    Values are pre-filled estimates, not authoritative: the recipe stays a draft
    the user reviews/edits/finalizes via the manual macro UI (#18).
    """
    if not isinstance(raw, dict):
        return {}
    lookup = {str(k).lower(): v for k, v in raw.items()}
    macros: dict[str, Decimal] = {}
    for key, field_name, parse in _NUTRIENT_FIELDS:
        parsed = parse(lookup.get(key))
        if parsed is not None:
            macros[field_name] = parsed
    return macros


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

    # Pre-fill per-serving macros from the page's published nutrition block when
    # present (#35). Missing/unparseable nutrition leaves the fields unset, so the
    # draft is identical to before for sites that don't publish it.
    macros = macros_from_nutrients(_safe(getattr(scraper, "nutrients", lambda: None)))

    return RecipeInput(
        title=title or "Untitled recipe",
        source_url=source_url,
        source_type=SourceType.WEB,
        servings=_parse_servings(_safe(getattr(scraper, "yields", lambda: None))),
        status=RecipeStatus.DRAFT,
        instructions_md=instructions_md,
        ingredients=ingredients,
        **macros,
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
        # (tests inject a fake scraper and never reach this path). The actual
        # parse (and its recipe_scrapers import) lives in `parse_html`.
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

        return self.parse_html(resp.text, url)

    def parse_html(self, html: str, url: str) -> RecipeInput:
        """Parse already-fetched page HTML into a draft (no network).

        Shared by `scrape` (after its own fetch) and the in-app-browser import
        path, which captures the rendered HTML from a real WebView and never
        needs a server-side fetch at all.
        """
        try:
            from recipe_scrapers import scrape_html
        except ImportError as exc:  # pragma: no cover - import guard
            raise ScrapeError(
                "recipe-scrapers is not installed; run `pip install recipe-scrapers`."
            ) from exc

        try:
            scraper = scrape_html(html, org_url=url, wild_mode=True)
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
