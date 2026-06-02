from decimal import Decimal

from recetario.infrastructure.nutrition.fdc_client import (
    parse_food_detail,
    parse_search_results,
)

_DETAIL = {
    "fdcId": 170000,
    "description": "Onions, raw",
    "dataType": "SR Legacy",
    "foodCategory": {"description": "Vegetables and Vegetable Products"},
    "foodNutrients": [
        {"nutrient": {"id": 1008, "name": "Energy", "unitName": "kcal"}, "amount": 40},
        {"nutrient": {"id": 1003, "name": "Protein", "unitName": "g"}, "amount": 1.1},
        {"nutrient": {"id": 1004, "name": "Total lipid (fat)", "unitName": "g"}, "amount": 0.1},
        {"nutrient": {"id": 1005, "name": "Carbohydrate", "unitName": "g"}, "amount": 9.34},
        {"nutrient": {"id": 1093, "name": "Sodium, Na", "unitName": "mg"}, "amount": 4},
        {"nutrient": {"id": 1063, "name": "Sugars, Total", "unitName": "g"}, "amount": 4.24},
        # Second "sugar" id maps to same canonical name -> must be dropped.
        {"nutrient": {"id": 2000, "name": "Sugars NLEA", "unitName": "g"}, "amount": 4.20},
        # Untracked micronutrient -> must be dropped.
        {"nutrient": {"id": 1051, "name": "Water", "unitName": "g"}, "amount": 89.11},
    ],
    "foodPortions": [
        {"portionDescription": "1 cup, chopped", "gramWeight": 160},
        {"amount": 1, "modifier": "slice", "measureUnit": {"name": "undetermined"}, "gramWeight": 14},
    ],
}


def test_parse_food_detail_keeps_only_tracked_nutrients():
    detail = parse_food_detail(_DETAIL)

    assert detail.fdc_id == 170000
    assert detail.category == "Vegetables and Vegetable Products"

    names = [n.name for n in detail.nutrients]
    assert names.count("sugar") == 1  # duplicate canonical collapsed
    assert "water" not in names
    assert set(names) == {"calories", "protein", "fat", "carbohydrate", "sodium", "sugar"}

    calories = next(n for n in detail.nutrients if n.name == "calories")
    assert calories.amount == Decimal("40")
    assert isinstance(calories.amount, Decimal)


def test_parse_food_detail_portions():
    detail = parse_food_detail(_DETAIL)
    labels = [(p.description, p.gram_weight) for p in detail.portions]
    assert labels[0] == ("1 cup, chopped", Decimal("160"))
    # "undetermined" measure unit is filtered out of the synthesized label.
    assert labels[1] == ("1 slice", Decimal("14"))


def test_parse_search_results_skips_incomplete_hits():
    data = {
        "foods": [
            {"fdcId": 170000, "description": "Onions, raw", "dataType": "SR Legacy"},
            {"description": "missing id"},
            {"fdcId": 99},
        ]
    }
    results = parse_search_results(data)
    assert len(results) == 1
    assert results[0].fdc_id == 170000
