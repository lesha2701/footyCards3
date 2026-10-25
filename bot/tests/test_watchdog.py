from datetime import datetime, timedelta

from services import watchdog
from services.watchdog import Watch, digest_text


def test_alerts_once_after_three_failed_checks_then_reports_recovery():
    watch = Watch()
    t0 = datetime(2026, 10, 25, 12, 0)
    assert watch.step(False, t0) is None
    assert watch.step(False, t0 + timedelta(minutes=1)) is None
    alert = watch.step(False, t0 + timedelta(minutes=2))
    assert alert and "не отвечает" in alert and "12:00" in alert
    assert watch.step(False, t0 + timedelta(minutes=3)) is None  # no repeat while down
    back = watch.step(True, t0 + timedelta(minutes=10))
    assert back and "снова работает" in back and "10 мин" in back
    assert watch.step(True, t0 + timedelta(minutes=11)) is None


def test_a_short_blip_says_nothing():
    watch = Watch()
    t0 = datetime(2026, 10, 25, 12, 0)
    assert watch.step(False, t0) is None
    assert watch.step(True, t0 + timedelta(minutes=1)) is None


def test_digest_lists_top_paths_and_is_silent_without_errors():
    assert digest_text([], 0) is None
    rows = [{"method": "GET", "path": "/api/v1/kontra/{id}", "count": 7, "last_error": "KeyError: 'x'"}]
    text = digest_text(rows, 9)
    assert "9" in text and "7×" in text and "/api/v1/kontra/{id}" in text and "KeyError" in text


def test_health_url_points_at_the_deep_check(monkeypatch):
    monkeypatch.setattr(watchdog.settings, "internal_backend_url", "http://backend:8000/api/v1")
    assert watchdog.health_url() == "http://backend:8000/api/health/deep"
