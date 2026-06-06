"""Unit tests for URL type detection + transcript → draft mapping (no network)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from recetario.application.ports import ExtractError
from recetario.domain.entities import IngestionInputType, RecipeStatus, SourceType
from recetario.application.use_cases.ingestion import detect_input_type
from recetario.infrastructure.llm import recipe_from_transcript, recipe_from_web


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://m.youtube.com/watch?v=abc",
        "https://vimeo.com/12345",
        "https://www.tiktok.com/@chef/video/123",
        "https://www.instagram.com/reel/xyz/",
    ],
)
def test_detect_video_hosts(url):
    assert detect_input_type(url) is IngestionInputType.VIDEO


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bbcgoodfood.com/recipes/garlic-soup",
        "https://example.com/blog/post",
        "https://notyoutube.com/watch",  # superstring host must not match
    ],
)
def test_detect_web_hosts(url):
    assert detect_input_type(url) is IngestionInputType.WEB


def test_recipe_from_transcript_builds_video_draft():
    payload = {
        "title": "  Garlic Soup  ",
        "servings": 4,
        "ingredients": [
            {"name": "garlic", "quantity": 2, "unit": "clove", "raw_text": "two cloves of garlic"},
            {"name": "salt", "quantity": None, "unit": None, "raw_text": "a pinch of salt"},
        ],
        "steps": ["Sauté the garlic.", " Add water and simmer. "],
    }
    draft = recipe_from_transcript(payload, source_url="https://youtu.be/abc")

    assert draft.title == "Garlic Soup"
    assert draft.servings == 4
    assert draft.source_type is SourceType.VIDEO
    assert draft.status is RecipeStatus.DRAFT
    assert draft.source_url == "https://youtu.be/abc"
    assert draft.instructions_md == "Sauté the garlic.\nAdd water and simmer."

    garlic, salt = draft.ingredients
    assert garlic.name == "garlic"
    assert garlic.quantity == Decimal("2")
    assert garlic.unit == "clove"
    assert garlic.raw_text == "two cloves of garlic"
    assert salt.quantity is None


def test_recipe_from_transcript_defaults_title_and_handles_no_steps():
    payload = {
        "title": "",
        "servings": None,
        "ingredients": [{"name": "water", "quantity": 1, "unit": "cup", "raw_text": "a cup of water"}],
        "steps": [],
    }
    draft = recipe_from_transcript(payload, source_url=None)
    assert draft.title == "Untitled recipe"
    assert draft.servings is None
    assert draft.instructions_md is None


def test_recipe_from_transcript_raises_when_no_ingredients():
    payload = {"title": "Not a recipe", "servings": None, "ingredients": [], "steps": []}
    with pytest.raises(ExtractError):
        recipe_from_transcript(payload, source_url=None)


def test_recipe_from_web_builds_web_draft():
    # The web fallback shares the extraction schema but tags the draft as WEB.
    payload = {
        "title": "Garlic Soup",
        "servings": 4,
        "ingredients": [
            {"name": "garlic", "quantity": 2, "unit": "clove", "raw_text": "2 cloves garlic"},
        ],
        "steps": ["Boil.", "Serve."],
    }
    draft = recipe_from_web(payload, source_url="https://example.com/soup")

    assert draft.title == "Garlic Soup"
    assert draft.servings == 4
    assert draft.source_type is SourceType.WEB
    assert draft.status is RecipeStatus.DRAFT
    assert draft.source_url == "https://example.com/soup"
    assert draft.instructions_md == "Boil.\nServe."
    assert draft.ingredients[0].quantity == Decimal("2")


def test_recipe_from_web_raises_when_no_ingredients():
    payload = {"title": "A blog post", "servings": None, "ingredients": [], "steps": []}
    with pytest.raises(ExtractError):
        recipe_from_web(payload, source_url="https://example.com/blog")
