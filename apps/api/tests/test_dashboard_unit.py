from datetime import date

from app.schemas.dashboard import DashboardCategory, DashboardProduct, DashboardResponse
from app.services.dashboard import _next_month, dashboard_csv


def test_next_month_handles_year_boundary() -> None:
    assert _next_month(2026, 7) == date(2026, 8, 1)
    assert _next_month(2026, 12) == date(2027, 1, 1)


def test_dashboard_response_accepts_empty_period() -> None:
    response = DashboardResponse(
        year=2026,
        month=7,
        currency="EUR",
        month_expense="0",
        previous_month_expense="0",
        month_change_percentage=None,
        month_income="0",
        month_balance="0",
        year_expense="0",
        receipt_count=0,
        average_receipt="0",
        largest_receipt="0",
        draft_count=0,
        excluded_currency_count=0,
        categories=[],
        monthly_trend=[],
        top_merchants_month=[],
        top_merchants_year=[],
        top_products=[],
    )

    assert response.categories == []


def test_category_percentage_is_explicit() -> None:
    category = DashboardCategory(category="groceries", amount="25", percentage="50")
    assert category.category == "groceries"
    assert category.percentage == 50


def test_csv_export_contains_sections_and_escapes_formula_text() -> None:
    response = DashboardResponse(
        year=2026, month=7, currency="EUR", month_expense="10",
        previous_month_expense="5", month_change_percentage="100",
        month_income="20", month_balance="10", year_expense="30",
        receipt_count=1, average_receipt="10", largest_receipt="10",
        draft_count=0, excluded_currency_count=0, categories=[],
        monthly_trend=[], top_merchants_month=[], top_merchants_year=[],
        top_products=[],
    )
    response.top_products.append(DashboardProduct(
        description="=DANGEROUS()", quantity=1,
        purchase_count=1, amount="10",
    ))

    exported = dashboard_csv(response)

    assert exported.startswith("\ufeff")
    assert "CATEGORY BREAKDOWN" in exported
    assert "MONTHLY TREND" in exported
    assert "'=DANGEROUS()" in exported
