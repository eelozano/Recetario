"""ShoppingAggregator — collapse a week's recipe ingredients into a grocery list.

Pure domain service. It is fed `ShoppingDemand`s (one per recipe ingredient line,
already scaled for the planned servings by the application layer) and groups them
by canonical ingredient *and unit*, summing quantities.

Why group by unit too: we have no density data, so we cannot honestly convert
"2 cups" + "100 g" of the same ingredient into one number. Lines that share a
unit are summed; lines in different units stay as separate, clearly-labelled
items. Quantity-less lines ("salt to taste") are preserved as un-summed items.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ShoppingDemand:
    ingredient_name: str
    normalized_name: str
    quantity: Decimal | None
    unit: str | None
    ingredient_id: int | None = None
    source_event_id: int | None = None


@dataclass(frozen=True)
class AggregatedItem:
    ingredient_name: str
    unit: str | None
    total_quantity: Decimal | None
    ingredient_id: int | None
    source_event_ids: list[int]


def _unit_key(unit: str | None) -> str | None:
    if unit is None:
        return None
    cleaned = unit.strip().lower()
    return cleaned or None


class ShoppingAggregator:
    def aggregate(self, demands: Sequence[ShoppingDemand]) -> list[AggregatedItem]:
        groups: dict[tuple[str, str | None], list[ShoppingDemand]] = {}
        order: list[tuple[str, str | None]] = []
        for demand in demands:
            key = (demand.normalized_name, _unit_key(demand.unit))
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(demand)

        items: list[AggregatedItem] = []
        for key in order:
            members = groups[key]
            quantities = [m.quantity for m in members if m.quantity is not None]
            total = sum(quantities, Decimal(0)) if quantities else None

            ingredient_id = next(
                (m.ingredient_id for m in members if m.ingredient_id is not None), None
            )
            event_ids: list[int] = []
            for m in members:
                if m.source_event_id is not None and m.source_event_id not in event_ids:
                    event_ids.append(m.source_event_id)

            items.append(
                AggregatedItem(
                    ingredient_name=members[0].ingredient_name,
                    unit=members[0].unit,
                    total_quantity=total,
                    ingredient_id=ingredient_id,
                    source_event_ids=event_ids,
                )
            )

        # Alphabetical for a shopper-friendly list.
        items.sort(key=lambda i: i.ingredient_name.lower())
        return items
