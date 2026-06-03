"""Claude-backed recipe extractor (implements the LlmRecipeExtractor port).

Three LLM passes, all grounded so the output stays reviewable:

* `structure` — refines a scraped draft, parsing each raw ingredient line into
  quantity/unit/name and tidying the title/servings. Constrained to a JSON
  schema via `output_config.format`, so the response is always valid JSON.
* `extract_from_transcript` — turns a free-form video transcript (captions) into
  a structured draft (title, servings, parsed ingredients, steps), same schema.
* `resolve_nutrition` — matches each ingredient to a USDA FoodData Central entry.
  Claude drives a `search_usda` tool (backed by the live `NutritionProvider`)
  in an agentic loop, then emits a structured list of {index, fdc_id,
  gram_weight, confidence}. The use case applies only confident matches.

The JSON→DTO mapping lives in module-level pure functions (`apply_structured`,
`recipe_from_transcript`, `parse_resolved`) so it is unit-tested against fixtures
without any network or SDK. The `anthropic` SDK is imported lazily so mocked
tests never need it.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from recetario.application.dto import (
    FoodSummary,
    RecipeIngredientInput,
    RecipeInput,
    ResolvedIngredient,
)
from recetario.application.ports import ExtractError, NutritionProvider
from recetario.domain.entities import RecipeStatus, SourceType

_DEFAULT_MODEL = "claude-sonnet-4-6"

_STRUCTURE_SYSTEM = (
    "You normalize scraped recipe drafts. For each ingredient line, extract a "
    "numeric quantity, a unit, and the bare ingredient name (drop quantities and "
    "units from the name). Keep the original line verbatim as raw_text. Use null "
    "for a quantity or unit that is absent or non-numeric (e.g. 'to taste'). Do "
    "not invent ingredients, steps, or servings — only restructure what is given."
)

_EXTRACT_SYSTEM = (
    "You extract a single recipe from a video transcript (auto-captions, so the "
    "text may be messy, repetitive, or lack punctuation). Produce a clean title, "
    "the number of servings if stated (else null), an ordered ingredient list, "
    "and ordered preparation steps. For each ingredient give a numeric quantity, "
    "a unit, and the bare ingredient name; use null for a quantity or unit that "
    "is not stated. Set raw_text to the phrase from the transcript that mentions "
    "the ingredient (or the name if there is no distinct phrase). Only include "
    "ingredients and steps actually described in the transcript — never invent "
    "amounts or steps. If the transcript is not a recipe, return an empty "
    "ingredients array."
)

_RESOLUTION_SYSTEM = (
    "You match recipe ingredients to USDA FoodData Central foods. Use the "
    "search_usda tool to find candidates for each ingredient (search by the bare "
    "food name, e.g. 'garlic' not '2 cloves garlic, minced'). Pick the single "
    "generic whole-food entry that best matches; prefer SR Legacy / Foundation "
    "items over anything oddly specific. Estimate gram_weight as the total grams "
    "the recipe uses for that line (convert the parsed quantity/unit to grams; if "
    "you cannot, use null). Report confidence in [0,1]: use a low value when the "
    "ingredient is vague, no good candidate exists, or the quantity is unclear. "
    "When unsure, return fdc_id null rather than guessing."
)

_STRUCTURE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "servings": {"type": ["integer", "null"]},
            "ingredients": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": ["number", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "raw_text": {"type": "string"},
                    },
                    "required": ["name", "quantity", "unit", "raw_text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "servings", "ingredients"],
        "additionalProperties": False,
    },
}

_EXTRACT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "servings": {"type": ["integer", "null"]},
            "ingredients": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": ["number", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "raw_text": {"type": "string"},
                    },
                    "required": ["name", "quantity", "unit", "raw_text"],
                    "additionalProperties": False,
                },
            },
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "servings", "ingredients", "steps"],
        "additionalProperties": False,
    },
}

_RESOLUTION_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "fdc_id": {"type": ["integer", "null"]},
                        "gram_weight": {"type": ["number", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["index", "fdc_id", "gram_weight", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["matches"],
        "additionalProperties": False,
    },
}

_SEARCH_TOOL: dict[str, Any] = {
    "name": "search_usda",
    "description": "Search USDA FoodData Central for foods matching a query. "
    "Returns up to page_size candidates as {fdc_id, description, data_type}.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "page_size": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _ingredients_from_items(items: Any) -> list[RecipeIngredientInput]:
    """Map an LLM ingredients array into DTOs, dropping unnamed rows."""
    if not isinstance(items, list):
        raise ExtractError("Response had no ingredients array.")
    return [
        RecipeIngredientInput(
            name=str(item.get("name", "")).strip(),
            quantity=_to_decimal(item.get("quantity")),
            unit=(str(item["unit"]).strip() or None) if item.get("unit") else None,
            raw_text=(str(item.get("raw_text", "")).strip() or None),
        )
        for item in items
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]


def apply_structured(draft: RecipeInput, payload: dict[str, Any]) -> RecipeInput:
    """Fold the LLM's structuring JSON back onto the scraped draft.

    Carries over everything the LLM does not touch (source, status, steps, tags).
    """
    ingredients = _ingredients_from_items(payload.get("ingredients"))

    title = payload.get("title")
    title = title.strip() if isinstance(title, str) and title.strip() else draft.title

    servings = payload.get("servings")
    servings = servings if isinstance(servings, int) else draft.servings

    return RecipeInput(
        title=title,
        description=draft.description,
        source_url=draft.source_url,
        source_type=draft.source_type,
        servings=servings,
        rating=draft.rating,
        status=draft.status,
        instructions_md=draft.instructions_md,
        ingredients=ingredients or draft.ingredients,
        tags=list(draft.tags),
    )


def recipe_from_transcript(
    payload: dict[str, Any], *, source_url: str | None
) -> RecipeInput:
    """Build a draft RecipeInput from the transcript-extraction JSON.

    Raises ExtractError if the transcript yielded no recipe (no ingredients) so
    the video job fails cleanly rather than persisting an empty draft.
    """
    ingredients = _ingredients_from_items(payload.get("ingredients"))
    if not ingredients:
        raise ExtractError("No recipe could be extracted from the video transcript.")

    title = payload.get("title")
    title = title.strip() if isinstance(title, str) and title.strip() else "Untitled recipe"

    servings = payload.get("servings")
    servings = servings if isinstance(servings, int) else None

    steps = payload.get("steps")
    step_lines = (
        [s.strip() for s in steps if isinstance(s, str) and s.strip()]
        if isinstance(steps, list)
        else []
    )
    instructions_md = "\n".join(step_lines) if step_lines else None

    return RecipeInput(
        title=title,
        source_url=source_url,
        source_type=SourceType.VIDEO,
        servings=servings,
        status=RecipeStatus.DRAFT,
        instructions_md=instructions_md,
        ingredients=ingredients,
    )


def parse_resolved(payload: dict[str, Any], count: int) -> list[ResolvedIngredient]:
    """Map the matches JSON into ResolvedIngredient, dropping out-of-range rows."""
    rows = payload.get("matches")
    if not isinstance(rows, list):
        raise ExtractError("Resolution response had no matches array.")

    resolved: list[ResolvedIngredient] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = row.get("index")
        if not isinstance(index, int) or not 0 <= index < count:
            continue
        fdc_id = row.get("fdc_id")
        fdc_id = int(fdc_id) if isinstance(fdc_id, int) else None
        confidence = row.get("confidence")
        confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
        resolved.append(
            ResolvedIngredient(
                index=index,
                fdc_id=fdc_id,
                gram_weight=_to_decimal(row.get("gram_weight")),
                confidence=min(max(confidence, 0.0), 1.0),
            )
        )
    return resolved


def _structure_prompt(draft: RecipeInput) -> str:
    lines = [i.raw_text or i.name for i in draft.ingredients]
    return json.dumps(
        {
            "title": draft.title,
            "servings": draft.servings,
            "ingredient_lines": lines,
        },
        ensure_ascii=False,
    )


def _resolution_prompt(ingredients: list[RecipeIngredientInput]) -> str:
    rows = [
        {
            "index": idx,
            "name": ing.name,
            "quantity": str(ing.quantity) if ing.quantity is not None else None,
            "unit": ing.unit,
        }
        for idx, ing in enumerate(ingredients)
    ]
    return (
        "Match each of these ingredients to a USDA food. Return one entry per "
        "index.\n" + json.dumps(rows, ensure_ascii=False)
    )


def _search_result_text(summaries: list[FoodSummary]) -> str:
    return json.dumps(
        [
            {"fdc_id": s.fdc_id, "description": s.description, "data_type": s.data_type}
            for s in summaries
        ],
        ensure_ascii=False,
    )


class AnthropicRecipeExtractor:
    """LlmRecipeExtractor backed by the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = 8000,
        max_tool_iterations: int = 8,
    ) -> None:
        if not api_key:
            raise ValueError("An Anthropic API key is required (set RECETARIO_ANTHROPIC_API_KEY).")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._max_tool_iterations = max_tool_iterations
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - import guard
                raise ExtractError(
                    "anthropic is not installed; run `pip install anthropic`."
                ) from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def structure(self, draft: RecipeInput) -> RecipeInput:
        if not draft.ingredients:
            return draft
        client = self._get_client()
        try:
            resp = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_STRUCTURE_SYSTEM,
                output_config={"format": _STRUCTURE_FORMAT},
                messages=[{"role": "user", "content": _structure_prompt(draft)}],
            )
        except Exception as exc:  # noqa: BLE001 - normalize to the port's error
            raise ExtractError(f"LLM structuring failed: {exc}") from exc
        return apply_structured(draft, _first_json(resp))

    def extract_from_transcript(
        self, transcript: str, *, source_url: str | None
    ) -> RecipeInput:
        if not transcript.strip():
            raise ExtractError("The transcript was empty.")
        client = self._get_client()
        prompt = "Extract the recipe from this video transcript:\n\n" + transcript
        try:
            resp = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_EXTRACT_SYSTEM,
                output_config={"format": _EXTRACT_FORMAT},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 - normalize to the port's error
            raise ExtractError(f"LLM transcript extraction failed: {exc}") from exc
        return recipe_from_transcript(_first_json(resp), source_url=source_url)

    def resolve_nutrition(
        self,
        ingredients: list[RecipeIngredientInput],
        search: NutritionProvider,
    ) -> list[ResolvedIngredient]:
        if not ingredients:
            return []
        client = self._get_client()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _resolution_prompt(ingredients)}
        ]
        try:
            for _ in range(self._max_tool_iterations):
                resp = client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=_RESOLUTION_SYSTEM,
                    tools=[_SEARCH_TOOL],
                    output_config={"format": _RESOLUTION_FORMAT},
                    messages=messages,
                )
                if resp.stop_reason != "tool_use":
                    return parse_resolved(_first_json(resp), len(ingredients))

                messages.append({"role": "assistant", "content": resp.content})
                messages.append(
                    {"role": "user", "content": _run_search_tools(resp.content, search)}
                )
        except ExtractError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize to the port's error
            raise ExtractError(f"LLM nutrition resolution failed: {exc}") from exc

        raise ExtractError("LLM exceeded the tool-iteration budget while resolving.")


def _run_search_tools(content: Any, search: NutritionProvider) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for block in content:
        if getattr(block, "type", None) != "tool_use" or block.name != "search_usda":
            continue
        args = block.input or {}
        query = str(args.get("query", "")).strip()
        page_size = args.get("page_size")
        kwargs = {"page_size": page_size} if isinstance(page_size, int) else {}
        try:
            summaries = search.search(query, **kwargs) if query else []
            result = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _search_result_text(summaries),
            }
        except Exception as exc:  # noqa: BLE001 - surface search failure to Claude
            result = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": f"Search failed: {exc}",
                "is_error": True,
            }
        results.append(result)
    return results


def _first_json(response: Any) -> dict[str, Any]:
    """output_config.format guarantees the first text block is valid JSON."""
    text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise ExtractError("LLM returned no structured output.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractError("LLM returned a non-object JSON payload.")
    return data
