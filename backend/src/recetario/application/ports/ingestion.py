"""Ingestion ports — the boundaries the ingestion use cases depend on.

`RecipeScraper` turns a source URL into a structured draft (`RecipeInput`); the
deterministic adapter uses recipe-scrapers/JSON-LD, and a later LLM adapter can
implement the same port for messy pages. `LlmRecipeExtractor` is the optional
LLM layer that refines that draft (parsing quantities/units) and matches each
ingredient line to a USDA food. `IngestionJobRepository` persists job state so
the API can poll progress.
"""

from __future__ import annotations

from typing import Protocol

from recetario.application.dto import RecipeIngredientInput, RecipeInput, ResolvedIngredient
from recetario.application.ports.nutrition import NutritionProvider
from recetario.domain.entities import IngestionJob


class ScrapeError(Exception):
    """Raised when a source URL cannot be fetched or parsed into a recipe."""


class TranscriptError(ScrapeError):
    """Raised when a video has no usable captions/transcript to extract from.

    Subclasses ScrapeError so the job runner records it as a clean, user-facing
    failure (same terminal-state handling as a failed web scrape).
    """


class ExtractError(Exception):
    """Raised when the LLM extractor cannot structure or resolve a draft.

    Enrichment is best-effort, so callers catch this and fall back to the
    deterministic draft rather than failing the whole ingestion job.
    """


class RecipeScraper(Protocol):
    def scrape(self, url: str) -> RecipeInput: ...

    def parse_html(self, html: str, url: str) -> RecipeInput:
        """Parse caller-supplied page HTML (no network fetch) into a draft.

        Used by the in-app-browser import path: a real WebView runs the page's
        JS (clearing Cloudflare-style challenges that block a server-side fetch),
        then hands us the rendered HTML to parse with the same deterministic
        scraper as `scrape`.
        """
        ...


class VideoTranscriptFetcher(Protocol):
    """Pulls a plain-text transcript from a video URL (captions, no ASR).

    Implementations use existing manual/auto captions (e.g. via yt-dlp) and raise
    `TranscriptError` when none are available — audio transcription (ASR) is a
    deferred fallback, not part of this port.
    """

    def fetch_transcript(self, url: str) -> str: ...


class LlmRecipeExtractor(Protocol):
    """The LLM decisions only — retrieval and persistence stay in the use case.

    `structure` refines a scraped draft (parsing each ingredient line into
    quantity/unit/name and tidying title/servings). `extract_from_web` is the
    fallback for pages the deterministic scraper can't parse: it turns the page's
    plain text into a structured draft. `extract_from_transcript` does the same
    for a free-form video transcript. `resolve_nutrition` matches each line to a
    USDA food, using the live `search` provider to look up candidates, and reports
    a per-line confidence so low matches can be deferred.
    """

    def structure(self, draft: RecipeInput) -> RecipeInput: ...

    def extract_from_web(
        self, page_text: str, *, source_url: str | None
    ) -> RecipeInput: ...

    def extract_from_transcript(
        self, transcript: str, *, source_url: str | None
    ) -> RecipeInput: ...

    def resolve_nutrition(
        self,
        ingredients: list[RecipeIngredientInput],
        search: NutritionProvider,
    ) -> list[ResolvedIngredient]: ...


class IngestionJobRepository(Protocol):
    def add(self, job: IngestionJob) -> IngestionJob: ...

    def get(self, job_id: int) -> IngestionJob | None: ...

    def update(self, job: IngestionJob) -> IngestionJob | None: ...

    def list(self) -> list[IngestionJob]: ...
