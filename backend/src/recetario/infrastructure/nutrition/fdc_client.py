"""USDA FoodData Central live API adapter (implements NutritionProvider).

The HTTP surface is thin; the JSON→DTO mapping lives in module-level pure
functions (`parse_search_results`, `parse_food_detail`) so it can be unit-tested
against recorded fixtures without touching the network.

We keep only a curated set of macro-relevant nutrients (see TRACKED_NUTRIENTS) to
avoid caching the ~150 micronutrients FDC returns per food.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from recetario.application.dto.nutrition_dto import (
    FoodDetail,
    FoodNutrient,
    FoodPortion,
    FoodSummary,
)

_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# Generic, single-ingredient foods live in these datasets. Branded foods are
# excluded — they balloon the result set and rarely match a parsed recipe line.
_DEFAULT_DATA_TYPES = ("SR Legacy", "Foundation")

# USDA nutrient id → our canonical macro name. When several ids map to the same
# canonical name (e.g. the two "sugars" variants), the first one present wins.
TRACKED_NUTRIENTS: dict[int, str] = {
    1008: "calories",
    1003: "protein",
    1004: "fat",
    1005: "carbohydrate",
    1079: "fiber",
    2000: "sugar",
    1063: "sugar",
    1258: "saturated_fat",
    1093: "sodium",
}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_search_results(data: dict[str, Any]) -> list[FoodSummary]:
    results: list[FoodSummary] = []
    for hit in data.get("foods", []):
        fdc_id = hit.get("fdcId")
        description = hit.get("description")
        if fdc_id is None or not description:
            continue
        results.append(
            FoodSummary(
                fdc_id=int(fdc_id),
                description=str(description),
                data_type=hit.get("dataType"),
            )
        )
    return results


def parse_food_detail(data: dict[str, Any]) -> FoodDetail:
    fdc_id = int(data["fdcId"])
    category = data.get("foodCategory")
    if isinstance(category, dict):
        category = category.get("description")

    nutrients: list[FoodNutrient] = []
    seen_canonical: set[str] = set()
    for fn in data.get("foodNutrients", []):
        nutrient = fn.get("nutrient") or {}
        usda_id = nutrient.get("id")
        if usda_id is None:
            continue
        canonical = TRACKED_NUTRIENTS.get(int(usda_id))
        if canonical is None or canonical in seen_canonical:
            continue
        amount = _to_decimal(fn.get("amount"))
        if amount is None:
            continue
        seen_canonical.add(canonical)
        nutrients.append(
            FoodNutrient(
                usda_nutrient_id=int(usda_id),
                name=canonical,
                unit=nutrient.get("unitName", ""),
                amount=amount,
            )
        )

    portions: list[FoodPortion] = []
    for fp in data.get("foodPortions", []):
        gram_weight = _to_decimal(fp.get("gramWeight"))
        if gram_weight is None:
            continue
        portions.append(
            FoodPortion(gram_weight=gram_weight, description=_portion_label(fp))
        )

    return FoodDetail(
        fdc_id=fdc_id,
        description=str(data.get("description", "")),
        data_type=data.get("dataType"),
        category=category,
        nutrients=nutrients,
        portions=portions,
    )


def _portion_label(portion: dict[str, Any]) -> str | None:
    if portion.get("portionDescription"):
        return str(portion["portionDescription"])
    amount = portion.get("amount")
    modifier = portion.get("modifier")
    measure = portion.get("measureUnit") or {}
    unit = measure.get("name")
    parts = [str(p) for p in (amount, unit, modifier) if p and p != "undetermined"]
    return " ".join(parts) or None


class UsdaFdcClient:
    """NutritionProvider backed by the live FDC HTTP API."""

    def __init__(self, api_key: str, *, base_url: str = _BASE_URL, timeout: float = 20.0) -> None:
        if not api_key:
            raise ValueError("A USDA FDC API key is required (set RECETARIO_FDC_API_KEY).")
        self._api_key = api_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def search(self, query: str, *, page_size: int = 5) -> list[FoodSummary]:
        resp = self._client.get(
            "/foods/search",
            params={
                "api_key": self._api_key,
                "query": query,
                "pageSize": page_size,
                "dataType": list(_DEFAULT_DATA_TYPES),
            },
        )
        resp.raise_for_status()
        return parse_search_results(resp.json())

    def get_food(self, fdc_id: int) -> FoodDetail | None:
        resp = self._client.get(
            f"/food/{fdc_id}",
            params={"api_key": self._api_key, "format": "full"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return parse_food_detail(resp.json())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UsdaFdcClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
