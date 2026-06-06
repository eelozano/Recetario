"""Builders for the optional, key-gated runtime adapters (LLM + live FDC).

Both live enrichments are opt-in: each factory returns ``None`` when its API key
is absent, and the app degrades gracefully (deterministic scraping only; cached
nutrition only). They live here — rather than inline in ``main.py`` — so the
Settings router can rebuild them on ``app.state`` the moment a user saves a key,
making the change take effect without restarting the sidecar.
"""

from __future__ import annotations

from collections.abc import Callable

from recetario.application.ports import LlmRecipeExtractor, NutritionProvider
from recetario.infrastructure.config import Settings


def make_extractor_factory(settings: Settings) -> Callable[[], LlmRecipeExtractor | None]:
    """LLM enrichment is opt-in: only built when an Anthropic key is configured."""
    if not settings.anthropic_api_key:
        return lambda: None

    def build() -> LlmRecipeExtractor | None:
        from recetario.infrastructure.llm import AnthropicRecipeExtractor

        return AnthropicRecipeExtractor(settings.anthropic_api_key, model=settings.anthropic_model)

    return build


def make_provider_factory(settings: Settings) -> Callable[[], NutritionProvider | None]:
    """USDA matching needs the live FDC provider; absent a key, it's unavailable."""
    if not settings.fdc_api_key:
        return lambda: None

    def build() -> NutritionProvider | None:
        from recetario.infrastructure.nutrition.fdc_client import UsdaFdcClient

        return UsdaFdcClient(settings.fdc_api_key)

    return build
