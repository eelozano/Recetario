from datetime import date
from decimal import Decimal

from recetario.domain.entities import MealType
from recetario.domain.services.meal_planner import MealPlanAggregator, PlannedMeal
from recetario.domain.value_objects.macro import MacroProfile


def _meal(d, *, servings, cals, protein=Decimal(0), meal_type=MealType.DINNER):
    return PlannedMeal(
        date=d,
        meal_type=meal_type,
        servings_planned=Decimal(servings),
        per_serving=MacroProfile({"calories": Decimal(cals), "protein": protein}),
    )


def test_scales_per_serving_by_planned_servings():
    agg = MealPlanAggregator()
    d = date(2026, 6, 1)
    summary = agg.aggregate([_meal(d, servings=2, cals=100, protein=Decimal(5))])

    assert summary.totals.amounts["calories"] == Decimal(200)
    assert summary.totals.amounts["protein"] == Decimal(10)
    assert len(summary.days) == 1
    assert summary.days[0].date == d


def test_groups_by_day_and_sums_week_total():
    agg = MealPlanAggregator()
    mon = date(2026, 6, 1)
    tue = date(2026, 6, 2)
    summary = agg.aggregate(
        [
            _meal(mon, servings=1, cals=300),
            _meal(mon, servings=1, cals=200, meal_type=MealType.LUNCH),
            _meal(tue, servings=2, cals=250),
        ]
    )

    # Two days, sorted ascending.
    assert [d.date for d in summary.days] == [mon, tue]
    assert summary.days[0].totals.amounts["calories"] == Decimal(500)  # 300 + 200
    assert summary.days[1].totals.amounts["calories"] == Decimal(500)  # 250 * 2
    assert summary.totals.amounts["calories"] == Decimal(1000)


def test_fractional_servings():
    agg = MealPlanAggregator()
    d = date(2026, 6, 1)
    summary = agg.aggregate([_meal(d, servings=Decimal("0.5"), cals=400)])
    assert summary.days[0].totals.amounts["calories"] == Decimal(200)


def test_empty_plan_is_zeroed():
    summary = MealPlanAggregator().aggregate([])
    assert summary.days == []
    assert summary.totals.amounts == {}
