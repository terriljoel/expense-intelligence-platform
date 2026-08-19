from app.services.diagnostics import clear_errors, recent_errors, record_error


def test_diagnostics_are_bounded_newest_first_and_clearable() -> None:
    clear_errors()
    for number in range(105):
        record_error(message=f"failure {number}", path="/test")

    entries = recent_errors(100)
    assert len(entries) == 100
    assert entries[0]["message"] == "failure 104"
    assert entries[-1]["message"] == "failure 5"

    clear_errors()
    assert recent_errors() == []


def test_diagnostic_exception_includes_traceback() -> None:
    clear_errors()
    try:
        raise ValueError("raw diagnostic detail")
    except ValueError as exc:
        error_id = record_error(message=str(exc), exception=exc)

    entry = recent_errors()[0]
    assert entry["id"] == error_id
    assert "ValueError: raw diagnostic detail" in entry["traceback"]
