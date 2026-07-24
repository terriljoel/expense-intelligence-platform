from app.services.maintenance import confirmation_phrase


def test_confirmation_phrase_contains_exact_household_name() -> None:
    assert confirmation_phrase("Family Berlin") == "RESET Family Berlin"


def test_confirmation_phrase_does_not_normalize_household_name() -> None:
    assert confirmation_phrase("  My Home  ") == "RESET   My Home  "
