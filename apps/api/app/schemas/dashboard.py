from decimal import Decimal

from pydantic import BaseModel


class DashboardMetric(BaseModel):
    label: str
    amount: Decimal
    count: int | None = None


class DashboardCategory(BaseModel):
    category: str
    amount: Decimal
    percentage: Decimal


class DashboardMerchant(BaseModel):
    merchant_id: str | None
    name: str
    address: str | None
    amount: Decimal
    receipt_count: int


class DashboardProduct(BaseModel):
    description: str
    quantity: Decimal
    purchase_count: int
    amount: Decimal


class DashboardTrendPoint(BaseModel):
    month: int
    label: str
    expense: Decimal
    income: Decimal


class DashboardResponse(BaseModel):
    year: int
    month: int
    currency: str
    month_expense: Decimal
    previous_month_expense: Decimal
    month_change_percentage: Decimal | None
    month_income: Decimal
    month_balance: Decimal
    year_expense: Decimal
    receipt_count: int
    average_receipt: Decimal
    largest_receipt: Decimal
    draft_count: int
    excluded_currency_count: int
    categories: list[DashboardCategory]
    monthly_trend: list[DashboardTrendPoint]
    top_merchants_month: list[DashboardMerchant]
    top_merchants_year: list[DashboardMerchant]
    top_products: list[DashboardProduct]

