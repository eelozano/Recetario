from decimal import Decimal

from recetario.domain.services.shopping_aggregator import ShoppingAggregator, ShoppingDemand


def _d(name, qty, unit, *, event=1, ingredient_id=None):
    return ShoppingDemand(
        ingredient_name=name,
        normalized_name=name.strip().lower(),
        quantity=Decimal(qty) if qty is not None else None,
        unit=unit,
        ingredient_id=ingredient_id,
        source_event_id=event,
    )


def test_sums_same_ingredient_and_unit():
    items = ShoppingAggregator().aggregate(
        [_d("Onion", 2, "pc", event=1), _d("Onion", 3, "pc", event=2)]
    )
    assert len(items) == 1
    assert items[0].ingredient_name == "Onion"
    assert items[0].total_quantity == Decimal(5)
    assert items[0].source_event_ids == [1, 2]


def test_same_ingredient_different_units_stay_separate():
    items = ShoppingAggregator().aggregate(
        [_d("Onion", 2, "pc"), _d("Onion", 100, "g")]
    )
    assert len(items) == 2
    units = {i.unit for i in items}
    assert units == {"pc", "g"}


def test_unit_grouping_is_case_insensitive():
    items = ShoppingAggregator().aggregate([_d("Flour", 1, "Cup"), _d("Flour", 2, "cup")])
    assert len(items) == 1
    assert items[0].total_quantity == Decimal(3)


def test_quantityless_items_preserved():
    items = ShoppingAggregator().aggregate([_d("Salt", None, None)])
    assert len(items) == 1
    assert items[0].total_quantity is None


def test_alphabetical_ordering():
    items = ShoppingAggregator().aggregate(
        [_d("Zucchini", 1, "pc"), _d("Apple", 1, "pc"), _d("Mango", 1, "pc")]
    )
    assert [i.ingredient_name for i in items] == ["Apple", "Mango", "Zucchini"]


def test_carries_first_ingredient_id():
    items = ShoppingAggregator().aggregate(
        [_d("Onion", 1, "pc", ingredient_id=None), _d("Onion", 1, "pc", ingredient_id=7)]
    )
    assert items[0].ingredient_id == 7


def test_dedupes_source_event_ids():
    items = ShoppingAggregator().aggregate(
        [_d("Onion", 1, "pc", event=5), _d("Onion", 1, "pc", event=5)]
    )
    assert items[0].source_event_ids == [5]
