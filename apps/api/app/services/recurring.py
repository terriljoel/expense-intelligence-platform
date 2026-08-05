from calendar import monthrange
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Receipt, RecurringExpense
from app.schemas.recurring import RecurringExpenseWrite
from app.services.receipt import add_receipt_item, create_receipt


def list_templates(session: Session, household_id: UUID) -> list[RecurringExpense]:
    return list(
        session.scalars(
            select(RecurringExpense)
            .where(RecurringExpense.household_id == household_id)
            .order_by(RecurringExpense.name)
        )
    )


def save_template(
    session: Session,
    household_id: UUID,
    user_id: UUID,
    data: RecurringExpenseWrite,
    template_id: UUID | None = None,
) -> RecurringExpense:
    template = (
        session.get(RecurringExpense, template_id)
        if template_id
        else RecurringExpense(household_id=household_id, created_by_user_id=user_id)
    )
    if template_id and (template is None or template.household_id != household_id):
        raise LookupError
    for key, value in data.model_dump().items():
        setattr(template, key, value)
    template.day_of_month = data.day_of_month or data.next_occurrence_date.day
    session.add(template)
    session.flush()
    return template


def generate_due(
    session: Session, household_id: UUID, through: date | None = None
) -> list[Receipt]:
    today, created = through or date.today(), []
    templates = session.scalars(
        select(RecurringExpense)
        .where(
            RecurringExpense.household_id == household_id,
            RecurringExpense.is_active.is_(True),
            RecurringExpense.next_occurrence_date <= today,
        )
        .with_for_update()
    ).all()
    for template in templates:
        for _ in range(366):
            due = template.next_occurrence_date
            if due > today:
                break
            exists = session.scalar(
                select(Receipt.id).where(
                    Receipt.recurring_template_id == template.id,
                    Receipt.recurring_occurrence_date == due,
                )
            )
            if not exists:
                receipt = create_receipt(
                    session,
                    household_id=household_id,
                    created_by_user_id=template.created_by_user_id,
                    merchant_id=template.merchant_id,
                    payment_method_id=template.payment_method_id,
                    category=template.category,
                    purchase_date=due,
                    currency=template.currency,
                    stated_total=template.amount,
                    notes=template.notes or f"Recurring: {template.name}",
                )
                receipt.recurring_template_id, receipt.recurring_occurrence_date = (
                    template.id,
                    due,
                )
                add_receipt_item(
                    session,
                    household_id=household_id,
                    receipt_id=receipt.id,
                    actor_user_id=template.created_by_user_id,
                    position=1,
                    line_type="product",
                    raw_description=template.name,
                    description=template.name,
                    raw_quantity_text="1",
                    quantity=1,
                    unit_price=template.amount,
                    line_total=template.amount,
                )
                created.append(receipt)
            template.next_occurrence_date = next_occurrence(
                due, template.frequency, template.day_of_month
            )
    session.flush()
    return created


def next_occurrence(value: date, frequency: str, day: int) -> date:
    if frequency == "daily":
        return value + timedelta(days=1)
    if frequency == "weekly":
        return value + timedelta(days=7)
    return _add_months(
        value, {"monthly": 1, "quarterly": 3, "yearly": 12}[frequency], day
    )


def _add_months(value: date, months: int, day: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(day, monthrange(year, month)[1]))
