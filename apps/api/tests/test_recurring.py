from datetime import date

import pytest

from app.services.recurring import next_occurrence


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        ("daily", date(2026, 2, 1)),
        ("weekly", date(2026, 2, 7)),
        ("monthly", date(2026, 2, 28)),
        ("quarterly", date(2026, 4, 30)),
        ("yearly", date(2027, 1, 31)),
    ],
)
def test_next_occurrence(frequency: str, expected: date) -> None:
    assert next_occurrence(date(2026, 1, 31), frequency, 31) == expected
