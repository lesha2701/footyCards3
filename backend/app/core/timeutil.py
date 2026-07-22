from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings

settings = get_settings()


def app_timezone() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def ensure_aware(dt: datetime) -> datetime:
    """SQLite (used in tests) returns naive datetimes even for
    DateTime(timezone=True) columns; Postgres does not. Every naive datetime
    in this codebase is UTC by convention (see models/mixins.py:utcnow), so
    treating naive as UTC here keeps comparisons correct on both backends."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def local_today(now_utc: datetime | None = None) -> date:
    now_utc = ensure_aware(now_utc) if now_utc else datetime.now(timezone.utc)
    return now_utc.astimezone(app_timezone()).date()
