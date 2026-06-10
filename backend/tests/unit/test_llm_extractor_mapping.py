"""Unit tests for the LLM JSON → DTO mapping (no network, no SDK)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from recetario.application.dto import RecipeIngredientInput, RecipeInput
from recetario.application.ports import ExtractError
from recetario.domain.entities import RecipeStatus, SourceType
from recetario.infrastructure.llm import apply_structured, parse_resolved
from recetario.infrastructure.llm.recipe_extractor import AnthropicRecipeExtractor


def _draft() -> RecipeInput:
    return RecipeInput(
        title="Scraped Soup",
        source_url="https://example.com/soup",
        source_type=SourceType.WEB,
        servings=2,
        status=RecipeStatus.DRAFT,
        instructions_md="Boil.\nServe.",
        ingredients=[
            RecipeIngredientInput(name="2 cloves garlic", raw_text="2 cloves garlic"),
            RecipeIngredientInput(name="salt to taste", raw_text="salt to taste"),
        ],
        tags=["soup"],
    )


def test_apply_structured_parses_quantities_and_preserves_draft_fields():
    payload = {
        "title": "Garlic Soup",
        "servings": 4,
        "ingredients": [
            {"name": "garlic", "quantity": 2, "unit": "clove", "raw_text": "2 cloves garlic"},
            {"name": "salt", "quantity": None, "unit": None, "raw_text": "salt to taste"},
        ],
    }
    result = apply_structured(_draft(), payload)

    assert result.title == "Garlic Soup"
    assert result.servings == 4
    # Untouched draft fields carry over.
    assert result.source_type == SourceType.WEB
    assert result.status == RecipeStatus.DRAFT
    assert result.instructions_md == "Boil.\nServe."
    assert result.tags == ["soup"]

    garlic, salt = result.ingredients
    assert garlic.name == "garlic"
    assert garlic.quantity == Decimal("2")
    assert garlic.unit == "clove"
    assert garlic.raw_text == "2 cloves garlic"
    assert salt.quantity is None
    assert salt.unit is None


def test_apply_structured_falls_back_to_draft_title_and_servings():
    payload = {
        "title": "   ",
        "servings": None,
        "ingredients": [{"name": "garlic", "quantity": 1, "unit": None, "raw_text": "garlic"}],
    }
    result = apply_structured(_draft(), payload)
    assert result.title == "Scraped Soup"
    assert result.servings == 2


def test_apply_structured_drops_nameless_rows_and_keeps_draft_when_all_empty():
    payload = {"title": "X", "servings": 1, "ingredients": [{"name": "  ", "quantity": 1, "unit": "g", "raw_text": ""}]}
    result = apply_structured(_draft(), payload)
    # No usable ingredient → keep the original draft ingredients rather than wipe them.
    assert [i.name for i in result.ingredients] == ["2 cloves garlic", "salt to taste"]


def test_apply_structured_raises_without_ingredients_array():
    with pytest.raises(ExtractError):
        apply_structured(_draft(), {"title": "X", "servings": 1})


def test_parse_resolved_maps_matches_and_clamps_confidence():
    payload = {
        "matches": [
            {"index": 0, "fdc_id": 1104647, "gram_weight": 6, "confidence": 0.92},
            {"index": 1, "fdc_id": None, "gram_weight": None, "confidence": 1.5},
        ]
    }
    resolved = parse_resolved(payload, count=2)

    assert resolved[0].index == 0
    assert resolved[0].fdc_id == 1104647
    assert resolved[0].gram_weight == Decimal("6")
    assert resolved[0].confidence == 0.92
    assert resolved[1].fdc_id is None
    assert resolved[1].confidence == 1.0  # clamped to [0, 1]


def test_parse_resolved_drops_out_of_range_indices():
    payload = {"matches": [{"index": 5, "fdc_id": 1, "gram_weight": 1, "confidence": 0.9}]}
    assert parse_resolved(payload, count=2) == []


def test_parse_resolved_raises_without_matches_array():
    with pytest.raises(ExtractError):
        parse_resolved({}, count=1)


# --- Model split: structuring runs on Haiku, extraction stays on Sonnet -------


class _Block:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Resp:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _RecordingClient:
    """Stands in for anthropic.Anthropic, recording each call's `model`."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.models: list[str] = []

    @property
    def messages(self):  # noqa: ANN202 - the SDK exposes `.messages.create`
        return self

    def create(self, **kwargs):  # noqa: ANN003, ANN202
        self.models.append(kwargs["model"])
        return _Resp(self._text)


_CANNED = json.dumps(
    {
        "title": "Garlic Soup",
        "servings": 1,
        "instructions_md": "Boil.",
        "ingredients": [
            {"name": "garlic", "quantity": 1, "unit": "clove", "raw_text": "1 clove garlic"}
        ],
    }
)


def _extractor_with_fake() -> AnthropicRecipeExtractor:
    ext = AnthropicRecipeExtractor(
        "test-key", model="extraction-model", structuring_model="structuring-model"
    )
    ext._client = _RecordingClient(_CANNED)  # bypass the lazy SDK import
    return ext


def test_structure_uses_the_structuring_model():
    ext = _extractor_with_fake()
    ext.structure(_draft())
    assert ext._client.models == ["structuring-model"]


def test_extraction_paths_use_the_extraction_model():
    ext = _extractor_with_fake()
    ext.extract_from_web("a page of text", source_url="https://example.com")
    ext.extract_from_transcript("a transcript", source_url="https://example.com")
    assert ext._client.models == ["extraction-model", "extraction-model"]


def test_structuring_model_defaults_to_the_extraction_model():
    ext = AnthropicRecipeExtractor("test-key", model="only-model")
    assert ext._structuring_model == "only-model"
