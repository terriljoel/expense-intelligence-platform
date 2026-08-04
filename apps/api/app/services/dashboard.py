from __future__ import annotations

import calendar
import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Household, IncomeEntry, Merchant, Product, Receipt, ReceiptItem
from app.schemas.dashboard import (
    DashboardCategory,
    DashboardBreakdown,
    DashboardMerchant,
    DashboardProduct,
    DashboardResponse,
    DashboardSpendPoint,
    DashboardTrendPoint,
)


ZERO = Decimal("0.00")


def _next_month(year: int, month: int) -> date:
    return date(year + (month == 12), 1 if month == 12 else month + 1, 1)


def _money(value: object) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _merchant_rows(
    session: Session,
    *,
    household_id: UUID,
    currency: str,
    start: date,
    end: date,
) -> list[DashboardMerchant]:
    rows = session.execute(
        select(
            Merchant.id,
            Merchant.name,
            Merchant.address,
            func.sum(Receipt.stated_total),
            func.count(Receipt.id),
        )
        .select_from(Receipt)
        .join(Merchant, Merchant.id == Receipt.merchant_id, isouter=True)
        .where(
            Receipt.household_id == household_id,
            Receipt.status == "approved",
            Receipt.currency == currency,
            Receipt.purchase_date >= start,
            Receipt.purchase_date < end,
        )
        .group_by(Merchant.id, Merchant.name, Merchant.address)
        .order_by(func.sum(Receipt.stated_total).desc())
        .limit(5)
    ).all()
    return [
        DashboardMerchant(
            merchant_id=str(row[0]) if row[0] else None,
            name=row[1] or "Unspecified merchant",
            address=row[2],
            amount=_money(row[3]),
            receipt_count=row[4],
        )
        for row in rows
    ]


def build_dashboard(
    session: Session, *, household_id: UUID, year: int, month: int
) -> DashboardResponse:
    household = session.get(Household, household_id)
    currency = household.default_currency if household else "EUR"
    month_start = date(year, month, 1)
    month_end = _next_month(year, month)
    previous_end = month_start
    previous_start = date(year - (month == 1), 12 if month == 1 else month - 1, 1)
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)

    month_total, receipt_count, average, largest = session.execute(
        select(
            func.coalesce(func.sum(Receipt.stated_total), 0),
            func.count(Receipt.id),
            func.coalesce(func.avg(Receipt.stated_total), 0),
            func.coalesce(func.max(Receipt.stated_total), 0),
        ).where(
            Receipt.household_id == household_id,
            Receipt.status == "approved",
            Receipt.currency == currency,
            Receipt.purchase_date >= month_start,
            Receipt.purchase_date < month_end,
        )
    ).one()
    previous_total = session.scalar(
        select(func.coalesce(func.sum(Receipt.stated_total), 0)).where(
            Receipt.household_id == household_id,
            Receipt.status == "approved",
            Receipt.currency == currency,
            Receipt.purchase_date >= previous_start,
            Receipt.purchase_date < previous_end,
        )
    )
    year_total = session.scalar(
        select(func.coalesce(func.sum(Receipt.stated_total), 0)).where(
            Receipt.household_id == household_id,
            Receipt.status == "approved",
            Receipt.currency == currency,
            Receipt.purchase_date >= year_start,
            Receipt.purchase_date < year_end,
        )
    )
    income_total = session.scalar(
        select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(
            IncomeEntry.household_id == household_id,
            IncomeEntry.currency == currency,
            IncomeEntry.received_date >= month_start,
            IncomeEntry.received_date < month_end,
        )
    )
    draft_count = (
        session.scalar(
            select(func.count(Receipt.id)).where(
                Receipt.household_id == household_id,
                Receipt.status == "draft",
            )
        )
        or 0
    )
    excluded_currency_count = (
        session.scalar(
            select(func.count(Receipt.id)).where(
                Receipt.household_id == household_id,
                Receipt.status == "approved",
                Receipt.currency != currency,
                Receipt.purchase_date >= month_start,
                Receipt.purchase_date < month_end,
            )
        )
        or 0
    )

    month_total = _money(month_total)
    previous_total = _money(previous_total)
    income_total = _money(income_total)
    category_rows = session.execute(
        select(Receipt.category, func.sum(Receipt.stated_total))
        .where(
            Receipt.household_id == household_id,
            Receipt.status == "approved",
            Receipt.currency == currency,
            Receipt.purchase_date >= month_start,
            Receipt.purchase_date < month_end,
        )
        .group_by(Receipt.category)
        .order_by(func.sum(Receipt.stated_total).desc())
    ).all()
    categories = [
        DashboardCategory(
            category=category,
            amount=_money(amount),
            percentage=(
                (_money(amount) / month_total * 100).quantize(Decimal("0.1"))
                if month_total
                else ZERO
            ),
        )
        for category, amount in category_rows
    ]

    expense_by_month = dict(
        session.execute(
            select(
                func.extract("month", Receipt.purchase_date),
                func.sum(Receipt.stated_total),
            )
            .where(
                Receipt.household_id == household_id,
                Receipt.status == "approved",
                Receipt.currency == currency,
                Receipt.purchase_date >= year_start,
                Receipt.purchase_date < year_end,
            )
            .group_by(func.extract("month", Receipt.purchase_date))
        ).all()
    )
    income_by_month = dict(
        session.execute(
            select(
                func.extract("month", IncomeEntry.received_date),
                func.sum(IncomeEntry.amount),
            )
            .where(
                IncomeEntry.household_id == household_id,
                IncomeEntry.currency == currency,
                IncomeEntry.received_date >= year_start,
                IncomeEntry.received_date < year_end,
            )
            .group_by(func.extract("month", IncomeEntry.received_date))
        ).all()
    )
    trend = [
        DashboardTrendPoint(
            month=index,
            label=calendar.month_abbr[index],
            expense=_money(expense_by_month.get(Decimal(index), 0)),
            income=_money(income_by_month.get(Decimal(index), 0)),
        )
        for index in range(1, 13)
    ]

    product_rows = session.execute(
        select(
            func.lower(func.btrim(ReceiptItem.description)).label("product"),
            func.sum(func.coalesce(ReceiptItem.quantity, 1)),
            func.count(func.distinct(ReceiptItem.receipt_id)),
            func.sum(ReceiptItem.line_total),
        )
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .where(
            ReceiptItem.household_id == household_id,
            Receipt.status == "approved",
            Receipt.currency == currency,
            Receipt.purchase_date >= month_start,
            Receipt.purchase_date < month_end,
            ReceiptItem.line_type == "product",
        )
        .group_by("product")
        .order_by(
            func.count(func.distinct(ReceiptItem.receipt_id)).desc(),
            func.sum(ReceiptItem.line_total).desc(),
        )
        .limit(8)
    ).all()
    products = [
        DashboardProduct(
            description=row[0],
            quantity=Decimal(row[1] or 0),
            purchase_count=row[2],
            amount=_money(row[3]),
        )
        for row in product_rows
    ]
    family_rows = session.execute(
        select(
            func.coalesce(Product.family_name, "Other groceries"),
            func.sum(ReceiptItem.line_total),
        )
        .select_from(ReceiptItem)
        .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
        .join(Product, Product.id == ReceiptItem.product_id, isouter=True)
        .where(
            ReceiptItem.household_id == household_id,
            Receipt.status == "approved",
            Receipt.category == "groceries",
            Receipt.currency == currency,
            Receipt.purchase_date >= month_start,
            Receipt.purchase_date < month_end,
            ReceiptItem.line_type == "product",
        )
        .group_by(Product.family_name)
        .order_by(func.sum(ReceiptItem.line_total).desc())
    ).all()
    grocery_total = sum((_money(row[1]) for row in family_rows), ZERO)
    families = [
        DashboardBreakdown(
            label=row[0],
            amount=_money(row[1]),
            percentage=(
                (_money(row[1]) / grocery_total * 100).quantize(Decimal("0.1"))
                if grocery_total
                else ZERO
            ),
        )
        for row in family_rows
    ]
    daily = dict(
        session.execute(
            select(Receipt.purchase_date, func.sum(Receipt.stated_total))
            .where(
                Receipt.household_id == household_id,
                Receipt.status == "approved",
                Receipt.currency == currency,
                Receipt.purchase_date >= month_start,
                Receipt.purchase_date < month_end,
            )
            .group_by(Receipt.purchase_date)
        ).all()
    )
    days = calendar.monthrange(year, month)[1]
    daily_spending = [
        DashboardSpendPoint(
            label=str(day), amount=_money(daily.get(date(year, month, day), 0))
        )
        for day in range(1, days + 1)
    ]
    weekly_spending = [
        DashboardSpendPoint(
            label=f"Week {week}",
            amount=sum(
                (point.amount for point in daily_spending[(week - 1) * 7 : week * 7]),
                ZERO,
            ),
        )
        for week in range(1, (days + 6) // 7 + 1)
    ]
    change = (
        None
        if previous_total == 0
        else ((month_total - previous_total) / previous_total * 100).quantize(
            Decimal("0.1")
        )
    )

    return DashboardResponse(
        year=year,
        month=month,
        currency=currency,
        month_expense=month_total,
        previous_month_expense=previous_total,
        month_change_percentage=change,
        month_income=income_total,
        month_balance=income_total - month_total,
        year_expense=_money(year_total),
        receipt_count=receipt_count,
        average_receipt=_money(average),
        largest_receipt=_money(largest),
        draft_count=draft_count,
        excluded_currency_count=excluded_currency_count,
        categories=categories,
        monthly_trend=trend,
        top_merchants_month=_merchant_rows(
            session,
            household_id=household_id,
            currency=currency,
            start=month_start,
            end=month_end,
        ),
        top_merchants_year=_merchant_rows(
            session,
            household_id=household_id,
            currency=currency,
            start=year_start,
            end=year_end,
        ),
        top_products=products,
        grocery_families=families,
        daily_spending=daily_spending,
        weekly_spending=weekly_spending,
    )


def dashboard_csv(data: DashboardResponse) -> str:
    """Create an Excel-friendly, formula-safe CSV dashboard report."""

    def safe(value: object) -> object:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return f"'{value}"
        return value

    output = StringIO(newline="")
    writer = csv.writer(output)

    def row(*values: object) -> None:
        writer.writerow([safe(value) for value in values])

    row("Expense Intelligence dashboard export")
    row("Period", f"{calendar.month_name[data.month]} {data.year}")
    row("Currency", data.currency)
    row()
    row("SUMMARY")
    row("Metric", "Value")
    row("Month expense", data.month_expense)
    row("Previous month expense", data.previous_month_expense)
    row("Month change percentage", data.month_change_percentage or "")
    row("Month income", data.month_income)
    row("Month balance", data.month_balance)
    row("Year expense", data.year_expense)
    row("Approved receipt count", data.receipt_count)
    row("Average receipt", data.average_receipt)
    row("Largest receipt", data.largest_receipt)
    row("Draft receipt count", data.draft_count)
    row("Other-currency receipts excluded", data.excluded_currency_count)
    row()
    row("CATEGORY BREAKDOWN")
    row("Category", "Amount", "Percentage")
    for item in data.categories:
        row(item.category, item.amount, item.percentage)
    row()
    row("TOP MERCHANTS - MONTH")
    row("Merchant", "Address", "Amount", "Receipt count")
    for item in data.top_merchants_month:
        row(item.name, item.address or "", item.amount, item.receipt_count)
    row()
    row("TOP MERCHANTS - YEAR")
    row("Merchant", "Address", "Amount", "Receipt count")
    for item in data.top_merchants_year:
        row(item.name, item.address or "", item.amount, item.receipt_count)
    row()
    row("MOST PURCHASED PRODUCTS - MONTH")
    row("Product", "Quantity", "Purchase count", "Amount")
    for item in data.top_products:
        row(item.description, item.quantity, item.purchase_count, item.amount)
    row()
    row("GROCERY FAMILY BREAKDOWN - MONTH")
    row("Family", "Amount", "Percentage")
    for item in data.grocery_families:
        row(item.label, item.amount, item.percentage)
    row()
    row("DAILY SPENDING - MONTH")
    row("Day", "Amount")
    for item in data.daily_spending:
        row(item.label, item.amount)
    row()
    row("WEEKLY SPENDING - MONTH")
    row("Week", "Amount")
    for item in data.weekly_spending:
        row(item.label, item.amount)
    row()
    row("MONTHLY TREND")
    row("Month", "Income", "Expense")
    for item in data.monthly_trend:
        row(item.label, item.income, item.expense)
    return "\ufeff" + output.getvalue()
