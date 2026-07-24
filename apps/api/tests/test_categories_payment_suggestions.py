from app.schemas.income import IncomeCreate
from app.schemas.receipt import ReceiptCreate
from app.services.receipt_capture import detect_payment_details


def test_detects_card_provider_and_last_four() -> None:
    assert detect_payment_details("VISA Karte **** 1234") == (
        "debit_card",
        "Visa",
        "1234",
    )


def test_detects_cash_without_inventing_card_details() -> None:
    assert detect_payment_details("ZAHLUNG BAR") == ("cash", None, None)


def test_transaction_category_defaults_remain_backward_compatible() -> None:
    receipt = ReceiptCreate(
        purchase_date="2026-07-23", currency="EUR", stated_total="12.00"
    )
    income = IncomeCreate(
        source="Employer",
        received_date="2026-07-23",
        amount="100.00",
        currency="EUR",
    )

    assert receipt.category == "other"
    assert income.category == "other"
