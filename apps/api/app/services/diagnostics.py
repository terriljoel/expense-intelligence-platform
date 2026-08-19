from collections import deque
from datetime import datetime, timezone
from threading import Lock
import traceback
from uuid import UUID, uuid4


_MAX_ENTRIES = 100
_entries: deque[dict[str, object]] = deque(maxlen=_MAX_ENTRIES)
_lock = Lock()


def record_error(
    *,
    message: str,
    method: str | None = None,
    path: str | None = None,
    status_code: int = 500,
    exception: BaseException | None = None,
    level: str = "error",
    household_id: UUID | None = None,
) -> str:
    error_id = uuid4().hex[:12]
    trace = (
        "".join(traceback.format_exception(exception))[-16000:]
        if exception is not None
        else None
    )
    entry = {
        "id": error_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "status_code": status_code,
        "method": method,
        "path": path,
        "message": message[:1000],
        "traceback": trace,
        "household_id": str(household_id) if household_id is not None else None,
    }
    with _lock:
        _entries.appendleft(entry)
    return error_id


def recent_errors(
    limit: int = 50,
    *,
    household_id: UUID | None = None,
) -> list[dict[str, object]]:
    with _lock:
        entries = list(_entries)
    if household_id is not None:
        entries = [
            entry for entry in entries if entry["household_id"] == str(household_id)
        ]
    return entries[: max(1, min(limit, _MAX_ENTRIES))]


def clear_errors(*, household_id: UUID | None = None) -> None:
    with _lock:
        if household_id is None:
            _entries.clear()
            return
        retained = [
            entry for entry in _entries if entry["household_id"] != str(household_id)
        ]
        _entries.clear()
        _entries.extend(retained)
