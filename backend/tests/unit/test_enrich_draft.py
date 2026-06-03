"""Unit tests for EnrichDraftRecipe orchestration (fakes, no network)."""

from __future__ import annotations

from decimal import Decimal

from recetario.application.dto import (
    FoodDetail,
    RecipeIngredientInput,
    RecipeInput,
    ResolvedIngredient,
)
from recetario.application.ports import ExtractError
from recetario.application.use_cases.ingestion import EnrichDraftRecipe
from recetario.domain.entities import RecipeStatus, SourceType


def _draft() -> RecipeInput:
    return RecipeInput(
        title="Soup",
        source_type=SourceType.WEB,
        status=RecipeStatus.DRAFT,
        ingredients=[
            RecipeIngredientInput(name="2 cloves garlic", raw_text="2 cloves garlic"),
            RecipeIngredientInput(name="parsley", raw_text="parsley"),
        ],
    )


class _FakeExtractor:
    def __init__(self, structured, resolved):
        self._structured = structured
        self._resolved = resolved
        self.structure_calls = 0

    def structure(self, draft):
        self.structure_calls += 1
        if isinstance(self._structured, Exception):
            raise self._structured
        return self._structured

    def resolve_nutrition(self, ingredients, search):
        if isinstance(self._resolved, Exception):
            raise self._resolved
        return self._resolved


class _FakeRepo:
    def __init__(self, cached=None):
        self._cached = cached or {}
        self.upserted: list[int] = []

    def get_food(self, fdc_id):
        return self._cached.get(fdc_id)

    def upsert_food(self, detail):
        self.upserted.append(detail.fdc_id)


class _FakeProvider:
    def __init__(self, foods=None):
        self._foods = foods or {}
        self.fetched: list[int] = []

    def search(self, query, *, page_size=5):
        return []

    def get_food(self, fdc_id):
        self.fetched.append(fdc_id)
        return self._foods.get(fdc_id)


def _structured() -> RecipeInput:
    draft = _draft()
    draft.ingredients[0] = RecipeIngredientInput(
        name="garlic", quantity=Decimal("2"), unit="clove", raw_text="2 cloves garlic"
    )
    return draft


def test_links_confident_match_and_caches_food():
    food = FoodDetail(fdc_id=1104647, description="Garlic, raw")
    extractor = _FakeExtractor(
        _structured(),
        [
            ResolvedIngredient(index=0, fdc_id=1104647, gram_weight=Decimal("6"), confidence=0.9),
            ResolvedIngredient(index=1, fdc_id=None, confidence=0.0),
        ],
    )
    provider = _FakeProvider(foods={1104647: food})
    repo = _FakeRepo()

    result = EnrichDraftRecipe(extractor, provider, repo)(_draft())

    garlic, parsley = result.ingredients
    assert garlic.usda_fdc_id == 1104647
    assert garlic.gram_weight == Decimal("6")
    assert repo.upserted == [1104647]
    assert provider.fetched == [1104647]  # cache miss → live fetch
    # Low-confidence / unmatched line is left unlinked for manual confirmation.
    assert parsley.usda_fdc_id is None


def test_low_confidence_match_is_not_linked():
    extractor = _FakeExtractor(
        _structured(),
        [ResolvedIngredient(index=0, fdc_id=1104647, gram_weight=Decimal("6"), confidence=0.4)],
    )
    provider = _FakeProvider(foods={1104647: FoodDetail(fdc_id=1104647, description="Garlic")})
    repo = _FakeRepo()

    result = EnrichDraftRecipe(extractor, provider, repo, min_confidence=0.6)(_draft())

    assert result.ingredients[0].usda_fdc_id is None
    assert repo.upserted == []
    assert provider.fetched == []


def test_uses_cached_food_without_live_fetch():
    food = FoodDetail(fdc_id=1104647, description="Garlic")
    extractor = _FakeExtractor(
        _structured(),
        [ResolvedIngredient(index=0, fdc_id=1104647, gram_weight=Decimal("6"), confidence=0.9)],
    )
    provider = _FakeProvider()  # would return None on get_food
    repo = _FakeRepo(cached={1104647: food})

    result = EnrichDraftRecipe(extractor, provider, repo)(_draft())

    assert result.ingredients[0].usda_fdc_id == 1104647
    assert provider.fetched == []  # served from cache
    assert repo.upserted == [1104647]


def test_structure_failure_falls_back_to_draft_then_still_resolves():
    extractor = _FakeExtractor(
        ExtractError("structuring down"),
        [ResolvedIngredient(index=0, fdc_id=1104647, gram_weight=Decimal("6"), confidence=0.9)],
    )
    provider = _FakeProvider(foods={1104647: FoodDetail(fdc_id=1104647, description="Garlic")})
    repo = _FakeRepo()

    result = EnrichDraftRecipe(extractor, provider, repo)(_draft())

    # Fell back to the raw scraped line, but resolution still linked it.
    assert result.ingredients[0].name == "2 cloves garlic"
    assert result.ingredients[0].usda_fdc_id == 1104647


def test_resolution_failure_returns_structured_draft_unlinked():
    extractor = _FakeExtractor(_structured(), ExtractError("resolution down"))
    provider = _FakeProvider()
    repo = _FakeRepo()

    result = EnrichDraftRecipe(extractor, provider, repo)(_draft())

    assert result.ingredients[0].name == "garlic"  # structuring kept
    assert result.ingredients[0].usda_fdc_id is None
    assert repo.upserted == []
